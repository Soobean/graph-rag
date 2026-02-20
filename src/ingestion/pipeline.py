"""
Ingestion Pipeline

데이터 로드 -> 추출 -> 검증 -> 저장의 전체 과정을 오케스트레이션합니다.
트랜잭션 기반 저장과 배치 처리를 지원합니다.
"""

import asyncio
import logging
from typing import Any

from src.config import get_settings
from src.infrastructure.neo4j_client import Neo4jClient
from src.ingestion.extractor import GraphExtractor
from src.ingestion.loaders.base import BaseLoader
from src.ingestion.models import Document, ExtractedGraph

logger = logging.getLogger(__name__)

# 배치 처리 설정
DEFAULT_BATCH_SIZE = 50  # 한 번에 처리할 Document 수
DEFAULT_CONCURRENCY = 5  # 동시 LLM 호출 수


class IngestionPipeline:
    """
    Robust KG Ingestion Pipeline

    Workflow:
    1. Load: Source Adapter(BaseLoader)를 통해 Document 변환
    2. Extract: LLM을 통해 Graph Structure 추출 (with Validation)
    3. Save: Neo4j에 트랜잭션으로 Idempotent하게 저장 (MERGE)

    Features:
    - 트랜잭션 기반 저장 (원자성 보장)
    - 배치 처리 지원 (대용량 데이터 최적화)
    - 동시성 제어 (LLM API 호출 제한)
    - Label 기반 쿼리 최적화 (Neo4j 인덱스 활용)
    """

    def __init__(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        self.settings = get_settings()
        self.extractor = GraphExtractor()
        self.batch_size = batch_size
        self.concurrency = concurrency

        self.neo4j_uri = self.settings.neo4j_uri
        self.neo4j_auth = (self.settings.neo4j_user, self.settings.neo4j_password)

    async def run(self, loader: BaseLoader) -> dict[str, int]:
        """
        파이프라인 실행 (배치 + 동시성 처리)

        Args:
            loader: 데이터 로더 (BaseLoader 구현체)

        Returns:
            실행 결과 통계 {total_nodes, total_edges, failed_docs}
        """
        logger.info(f"Starting ingestion from loader: {loader.__class__.__name__}")

        client = Neo4jClient(
            uri=self.neo4j_uri,
            user=self.neo4j_auth[0],
            password=self.neo4j_auth[1],
            database=self.settings.neo4j_database,
        )
        await client.connect()

        stats = {"total_nodes": 0, "total_edges": 0, "failed_docs": 0}

        try:
            # Document를 배치로 그룹화
            batch = []
            for doc in loader.load():
                batch.append(doc)

                if len(batch) >= self.batch_size:
                    batch_stats = await self._process_batch(client, batch)
                    self._merge_stats(stats, batch_stats)
                    batch = []

            # 남은 배치 처리
            if batch:
                batch_stats = await self._process_batch(client, batch)
                self._merge_stats(stats, batch_stats)

            logger.info(
                f"Ingestion completed. "
                f"Nodes: {stats['total_nodes']}, "
                f"Edges: {stats['total_edges']}, "
                f"Failed: {stats['failed_docs']}"
            )
            return stats

        finally:
            await client.close()

    async def _process_batch(
        self, client: Neo4jClient, docs: list[Document]
    ) -> dict[str, int]:
        """
        배치 단위 처리 (동시성 제한 + 트랜잭션 저장)

        Args:
            client: Neo4j 클라이언트
            docs: 처리할 Document 리스트

        Returns:
            배치 처리 결과 통계
        """
        stats = {"total_nodes": 0, "total_edges": 0, "failed_docs": 0}

        # Semaphore로 동시성 제한 (LLM API Rate Limit 대응)
        semaphore = asyncio.Semaphore(self.concurrency)

        async def extract_with_limit(doc: Document) -> ExtractedGraph | None:
            async with semaphore:
                try:
                    return await self.extractor.extract(doc)
                except Exception as e:
                    logger.error(f"Extraction failed for {doc.metadata}: {e}")
                    return None

        # 동시에 추출 (Semaphore로 제한)
        tasks = [extract_with_limit(doc) for doc in docs]
        results = await asyncio.gather(*tasks)

        # 추출 결과를 하나의 그래프로 병합
        merged_graph = ExtractedGraph(nodes=[], edges=[])
        for graph in results:
            if graph is None:
                stats["failed_docs"] += 1
                continue
            if not graph.nodes and not graph.edges:
                continue
            merged_graph.nodes.extend(graph.nodes)
            merged_graph.edges.extend(graph.edges)

        # 트랜잭션으로 일괄 저장
        if merged_graph.nodes or merged_graph.edges:
            await self._save_graph_batch(client, merged_graph)
            stats["total_nodes"] += len(merged_graph.nodes)
            stats["total_edges"] += len(merged_graph.edges)

        return stats

    def _merge_stats(self, total: dict, batch: dict) -> None:
        """통계 병합"""
        total["total_nodes"] += batch["total_nodes"]
        total["total_edges"] += batch["total_edges"]
        total["failed_docs"] += batch["failed_docs"]

    async def _save_graph_batch(
        self, client: Neo4jClient, graph: ExtractedGraph
    ) -> None:
        """
        ExtractedGraph를 트랜잭션으로 일괄 저장 (UNWIND 활용)

        UNWIND를 사용하여 단일 쿼리로 배치 처리하여 성능 최적화
        """
        # 1. 노드를 Label별로 그룹화하여 배치 저장
        nodes_by_label: dict[str, list[dict[str, Any]]] = {}
        for node in graph.nodes:
            label = node.label.value
            if label not in nodes_by_label:
                nodes_by_label[label] = []
            nodes_by_label[label].append(
                {
                    "id": node.id,
                    "props": node.properties,
                    "source_file": node.source_metadata.get("source", "unknown"),
                    "source_row": node.source_metadata.get("row_index", 0),
                }
            )

        # Label별로 배치 MERGE
        for label, nodes_data in nodes_by_label.items():
            await self._batch_merge_nodes(client, label, nodes_data)

        # 2. 엣지를 RelationType별로 그룹화하여 배치 저장
        edges_by_type: dict[str, list[dict[str, Any]]] = {}
        for edge in graph.edges:
            rel_type = edge.type.value
            if rel_type not in edges_by_type:
                edges_by_type[rel_type] = []

            edge_data = {
                "src_id": edge.source_id,
                "tgt_id": edge.target_id,
                "props": {**edge.properties, "confidence": edge.confidence},
            }
            # Label 정보가 있으면 추가 (쿼리 최적화용)
            if edge.source_label:
                edge_data["src_label"] = edge.source_label.value
            if edge.target_label:
                edge_data["tgt_label"] = edge.target_label.value

            edges_by_type[rel_type].append(edge_data)

        # RelationType별로 배치 MERGE
        for rel_type, edges_data in edges_by_type.items():
            await self._batch_merge_edges(client, rel_type, edges_data)

    async def _batch_merge_nodes(
        self, client: Neo4jClient, label: str, nodes_data: list[dict]
    ) -> None:
        """
        동일 Label 노드들을 UNWIND로 일괄 MERGE

        Args:
            client: Neo4j 클라이언트
            label: 노드 Label
            nodes_data: 노드 데이터 리스트
        """
        query = f"""
        UNWIND $nodes AS node
        MERGE (n:{label} {{id: node.id}})
        ON CREATE SET
            n += node.props,
            n.created_at = datetime(),
            n.source_file = node.source_file,
            n.source_row = node.source_row
        ON MATCH SET
            n += node.props,
            n.updated_at = datetime(),
            n.last_source_file = node.source_file
        """

        await client.execute_write(query, {"nodes": nodes_data})
        logger.debug(f"Batch merged {len(nodes_data)} nodes with label {label}")

    async def _batch_merge_edges(
        self, client: Neo4jClient, rel_type: str, edges_data: list[dict]
    ) -> None:
        """
        동일 RelationType 엣지들을 UNWIND로 일괄 MERGE

        Label 정보가 있으면 활용하여 인덱스 기반 검색 수행

        Args:
            client: Neo4j 클라이언트
            rel_type: 관계 타입
            edges_data: 엣지 데이터 리스트
        """
        # Label 정보가 있는지 확인하여 최적화된 쿼리 선택
        # edges_data가 비어있으면 has_labels는 False
        has_labels = (
            len(edges_data) > 0
            and "src_label" in edges_data[0]
            and "tgt_label" in edges_data[0]
        )

        if has_labels:
            # Label 정보 활용 (인덱스 효율적)
            # 동일 타입의 엣지는 동일한 src_label, tgt_label을 가짐
            src_label = edges_data[0]["src_label"]
            tgt_label = edges_data[0]["tgt_label"]

            query = f"""
            UNWIND $edges AS edge
            MATCH (a:{src_label} {{id: edge.src_id}})
            MATCH (b:{tgt_label} {{id: edge.tgt_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            ON CREATE SET
                r += edge.props,
                r.created_at = datetime()
            ON MATCH SET
                r += edge.props,
                r.updated_at = datetime()
            """
        else:
            # Label 없이 범용 쿼리 (인덱스 비효율)
            query = f"""
            UNWIND $edges AS edge
            MATCH (a {{id: edge.src_id}})
            MATCH (b {{id: edge.tgt_id}})
            MERGE (a)-[r:{rel_type}]->(b)
            ON CREATE SET
                r += edge.props,
                r.created_at = datetime()
            ON MATCH SET
                r += edge.props,
                r.updated_at = datetime()
            """

        await client.execute_write(query, {"edges": edges_data})
        logger.debug(f"Batch merged {len(edges_data)} edges of type {rel_type}")
