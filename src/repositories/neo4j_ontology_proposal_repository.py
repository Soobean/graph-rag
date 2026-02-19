"""
Neo4j Ontology Proposal Repository - 온톨로지 제안 CRUD

책임:
- OntologyProposal 노드 저장/조회/수정
- 제안 상태 관리 (Optimistic Locking)
- 자동 승인 (일일 한도 포함)
- 페이지네이션/통계
"""

import logging
from typing import Any

from src.domain.adaptive.models import OntologyProposal, ProposalStatus
from src.domain.exceptions import QueryExecutionError, ValidationError
from src.infrastructure.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class Neo4jOntologyProposalRepository:
    """온톨로지 제안 CRUD 전담 레포지토리"""

    def __init__(self, client: Neo4jClient):
        self._client = client

    async def save_ontology_proposal(
        self,
        proposal: OntologyProposal,
    ) -> OntologyProposal:
        """온톨로지 제안 저장 (MERGE 패턴)"""
        query = """
        OPTIONAL MATCH (existing:OntologyProposal)
        WHERE toLower(existing.term) = toLower($term)
          AND toLower(existing.category) = toLower($category)
        WITH existing
        CALL {
            WITH existing
            WITH existing WHERE existing IS NOT NULL
            SET existing.version = existing.version + 1,
                existing.frequency = existing.frequency + 1,
                existing.evidence_questions = CASE
                    WHEN $question <> '' AND NOT $question IN COALESCE(existing.evidence_questions, [])
                    THEN COALESCE(existing.evidence_questions, []) + [$question]
                    ELSE COALESCE(existing.evidence_questions, [])
                END,
                existing.updated_at = datetime()
            RETURN existing AS p
          UNION
            WITH existing
            WITH existing WHERE existing IS NULL
            CREATE (new:OntologyProposal {
                id: $id,
                term: $term,
                category: $category,
                version: 1,
                proposal_type: $proposal_type,
                suggested_action: $suggested_action,
                suggested_parent: $suggested_parent,
                suggested_canonical: $suggested_canonical,
                evidence_questions: $evidence_questions,
                frequency: $frequency,
                confidence: $confidence,
                status: $status,
                source: $source,
                created_at: datetime(),
                updated_at: datetime()
            })
            RETURN new AS p
        }
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by
        """

        data = proposal.to_dict()
        evidence_questions = data.get("evidence_questions") or []
        question = evidence_questions[0] if evidence_questions else ""

        try:
            results = await self._client.execute_write(
                query,
                {
                    "id": data["id"],
                    "term": data["term"],
                    "category": data["category"],
                    "proposal_type": data["proposal_type"],
                    "suggested_action": data["suggested_action"],
                    "suggested_parent": data["suggested_parent"],
                    "suggested_canonical": data["suggested_canonical"],
                    "evidence_questions": data["evidence_questions"],
                    "frequency": data["frequency"],
                    "confidence": data["confidence"],
                    "status": data["status"],
                    "source": data["source"],
                    "question": question,
                },
            )

            if results:
                return OntologyProposal.from_dict(results[0])
            return proposal

        except Exception as e:
            logger.error(f"Failed to save ontology proposal: {e}")
            raise QueryExecutionError(
                f"Failed to save ontology proposal: {e}", query=query
            ) from e

    async def find_ontology_proposal(
        self,
        term: str,
        category: str,
    ) -> OntologyProposal | None:
        """term + category로 기존 제안 검색"""
        query = """
        MATCH (p:OntologyProposal)
        WHERE toLower(p.term) = toLower($term) AND toLower(p.category) = toLower($category)
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        """

        try:
            results = await self._client.execute_query(
                query, {"term": term, "category": category}
            )

            if results:
                return OntologyProposal.from_dict(results[0])
            return None

        except Exception as e:
            logger.error(f"Failed to find ontology proposal: {e}")
            return None

    async def update_proposal_frequency(
        self,
        proposal_id: str,
        question: str,
    ) -> bool:
        """제안의 빈도 증가 및 증거 질문 추가"""
        query = """
        MATCH (p:OntologyProposal {id: $id})
        SET
            p.frequency = p.frequency + 1,
            p.evidence_questions = CASE
                WHEN $question <> '' AND NOT $question IN COALESCE(p.evidence_questions, [])
                THEN COALESCE(p.evidence_questions, []) + [$question]
                ELSE COALESCE(p.evidence_questions, [])
            END,
            p.updated_at = datetime()
        RETURN p.id as id
        """

        try:
            results = await self._client.execute_write(
                query, {"id": proposal_id, "question": question}
            )
            return len(results) > 0

        except Exception as e:
            logger.error(f"Failed to update proposal frequency: {e}")
            return False

    async def update_proposal_status(
        self,
        proposal: OntologyProposal,
        expected_version: int,
    ) -> bool:
        """제안 상태 업데이트 (Optimistic Locking)"""
        if expected_version < 1:
            raise ValueError(f"expected_version must be >= 1, got {expected_version}")

        query = """
        MATCH (p:OntologyProposal {id: $id})
        WHERE p.version = $expected_version
        SET
            p.status = $status,
            p.version = p.version + 1,
            p.reviewed_at = $reviewed_at,
            p.reviewed_by = $reviewed_by,
            p.updated_at = datetime()
        RETURN p.id as id, p.version as new_version
        """

        data = proposal.to_dict()

        try:
            results = await self._client.execute_write(
                query,
                {
                    "id": data["id"],
                    "status": data["status"],
                    "reviewed_at": data["reviewed_at"],
                    "reviewed_by": data["reviewed_by"],
                    "expected_version": expected_version,
                },
            )

            if not results:
                logger.warning(
                    f"Optimistic lock failed for proposal {data['id']} "
                    f"(expected version: {expected_version})"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to update proposal status: {e}")
            return False

    async def count_today_auto_approved(self) -> int:
        """오늘 자동 승인된 제안 수 조회"""
        query = """
        MATCH (p:OntologyProposal)
        WHERE p.status = $status
          AND date(p.reviewed_at) = date()
        RETURN count(p) as count
        """

        try:
            results = await self._client.execute_query(
                query, {"status": ProposalStatus.AUTO_APPROVED.value}
            )

            if results:
                count = results[0].get("count", 0)
                return int(count) if count is not None else 0
            return 0

        except Exception as e:
            logger.error(f"Failed to count today's auto-approved proposals: {e}")
            return 0

    async def try_auto_approve_with_limit(
        self,
        proposal_id: str,
        expected_version: int,
        daily_limit: int,
    ) -> bool:
        """일일 한도를 확인하면서 원자적으로 자동 승인 (Race Condition 방지)"""
        if daily_limit <= 0:
            query = """
            MATCH (p:OntologyProposal {id: $proposal_id})
            WHERE p.version = $expected_version
            SET
                p.status = $new_status,
                p.version = p.version + 1,
                p.reviewed_at = datetime(),
                p.reviewed_by = 'system',
                p.updated_at = datetime()
            RETURN p.id as id
            """
            params = {
                "proposal_id": proposal_id,
                "expected_version": expected_version,
                "new_status": ProposalStatus.AUTO_APPROVED.value,
            }
        else:
            query = """
            // 오늘 자동 승인 수 카운트
            OPTIONAL MATCH (approved:OntologyProposal)
            WHERE approved.status = $auto_approved_status
              AND date(approved.reviewed_at) = date()
            WITH count(approved) as today_count

            // 한도 이하일 때만 타겟 제안 매칭
            MATCH (p:OntologyProposal {id: $proposal_id})
            WHERE today_count < $daily_limit
              AND p.version = $expected_version
            SET
                p.status = $new_status,
                p.version = p.version + 1,
                p.reviewed_at = datetime(),
                p.reviewed_by = 'system',
                p.updated_at = datetime()
            RETURN p.id as id, today_count
            """
            params = {
                "proposal_id": proposal_id,
                "expected_version": expected_version,
                "new_status": ProposalStatus.AUTO_APPROVED.value,
                "auto_approved_status": ProposalStatus.AUTO_APPROVED.value,
                "daily_limit": daily_limit,
            }

        try:
            results = await self._client.execute_write(query, params)

            if not results:
                logger.debug(
                    f"Auto-approve failed for {proposal_id}: "
                    f"limit exceeded or version mismatch (expected: {expected_version})"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to auto-approve proposal: {e}")
            return False

    async def get_pending_proposals(
        self,
        category: str | None = None,
        limit: int = 50,
    ) -> list[OntologyProposal]:
        """대기 중인 제안 목록 조회"""
        if category is not None:
            category = category.strip()
            if not category:
                raise ValidationError(
                    "Category cannot be empty string (use None for all)",
                    field="category",
                )

        query = """
        MATCH (p:OntologyProposal)
        WHERE p.status = $status
          AND ($category IS NULL OR p.category = $category)
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        ORDER BY p.frequency DESC, p.confidence DESC
        LIMIT $limit
        """

        try:
            results = await self._client.execute_query(
                query,
                {
                    "status": ProposalStatus.PENDING.value,
                    "category": category,
                    "limit": limit,
                },
            )

            return [OntologyProposal.from_dict(r) for r in results]

        except Exception as e:
            logger.error(f"Failed to get pending proposals: {e}")
            return []

    async def get_proposal_by_id(self, proposal_id: str) -> OntologyProposal | None:
        """ID로 단일 제안 조회"""
        query = """
        MATCH (p:OntologyProposal {id: $id})
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        """

        try:
            results = await self._client.execute_query(query, {"id": proposal_id})

            if results:
                return OntologyProposal.from_dict(results[0])
            return None

        except Exception as e:
            logger.error(f"Failed to get proposal by id {proposal_id}: {e}")
            return None

    async def get_proposals_paginated(
        self,
        status: str | None = None,
        proposal_type: str | None = None,
        source: str | None = None,
        category: str | None = None,
        term_search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[OntologyProposal], int]:
        """필터링 + 페이지네이션 목록 조회"""
        # SECURITY: 화이트리스트 기반 정렬 필드 검증
        allowed_sort_fields = {"created_at", "frequency", "confidence", "updated_at"}
        if sort_by not in allowed_sort_fields:
            sort_by = "created_at"

        sort_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

        count_query = """
        MATCH (p:OntologyProposal)
        WHERE ($status IS NULL OR p.status = $status)
          AND ($proposal_type IS NULL OR p.proposal_type = $proposal_type)
          AND ($source IS NULL OR p.source = $source)
          AND ($category IS NULL OR p.category = $category)
          AND ($term_search IS NULL OR toLower(p.term) CONTAINS toLower($term_search))
        RETURN count(p) as total
        """

        # NOTE: ORDER BY에서 f-string 사용 - sort_by/sort_direction은 위에서 화이트리스트 검증됨
        data_query = f"""
        MATCH (p:OntologyProposal)
        WHERE ($status IS NULL OR p.status = $status)
          AND ($proposal_type IS NULL OR p.proposal_type = $proposal_type)
          AND ($source IS NULL OR p.source = $source)
          AND ($category IS NULL OR p.category = $category)
          AND ($term_search IS NULL OR toLower(p.term) CONTAINS toLower($term_search))
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        ORDER BY p.{sort_by} {sort_direction}
        SKIP $offset
        LIMIT $limit
        """

        params = {
            "status": status,
            "proposal_type": proposal_type,
            "source": source,
            "category": category,
            "term_search": term_search,
            "offset": offset,
            "limit": limit,
        }

        try:
            count_results = await self._client.execute_query(count_query, params)
            total = count_results[0]["total"] if count_results else 0

            data_results = await self._client.execute_query(data_query, params)
            proposals = [OntologyProposal.from_dict(r) for r in data_results]

            return proposals, total

        except Exception as e:
            logger.error(f"Failed to get paginated proposals: {e}")
            return [], 0

    async def get_ontology_stats(self) -> dict[str, Any]:
        """온톨로지 통계 집계"""
        query = """
        // 상태별 카운트
        MATCH (p:OntologyProposal)
        WITH
            count(p) as total,
            sum(CASE WHEN p.status = 'pending' THEN 1 ELSE 0 END) as pending,
            sum(CASE WHEN p.status = 'approved' THEN 1 ELSE 0 END) as approved,
            sum(CASE WHEN p.status = 'auto_approved' THEN 1 ELSE 0 END) as auto_approved,
            sum(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) as rejected

        // 카테고리 분포 (별도 쿼리로 분리)
        OPTIONAL MATCH (p2:OntologyProposal)
        WITH total, pending, approved, auto_approved, rejected,
             collect({category: p2.category, status: p2.status}) as all_categories

        RETURN
            total,
            pending,
            approved,
            auto_approved,
            rejected,
            all_categories
        """

        top_terms_query = """
        MATCH (p:OntologyProposal)
        WHERE p.status = 'pending'
        RETURN p.term as term, p.category as category,
               p.frequency as frequency, p.confidence as confidence
        ORDER BY p.frequency DESC, p.confidence DESC
        LIMIT 10
        """

        try:
            stats_results = await self._client.execute_query(query, {})
            top_terms_results = await self._client.execute_query(top_terms_query, {})

            if not stats_results:
                return {
                    "total_proposals": 0,
                    "pending_count": 0,
                    "approved_count": 0,
                    "auto_approved_count": 0,
                    "rejected_count": 0,
                    "category_distribution": {},
                    "top_unresolved_terms": [],
                }

            stats = stats_results[0]

            category_dist: dict[str, int] = {}
            for item in stats.get("all_categories", []):
                if item and item.get("category"):
                    cat = item["category"]
                    category_dist[cat] = category_dist.get(cat, 0) + 1

            return {
                "total_proposals": stats.get("total", 0),
                "pending_count": stats.get("pending", 0),
                "approved_count": stats.get("approved", 0),
                "auto_approved_count": stats.get("auto_approved", 0),
                "rejected_count": stats.get("rejected", 0),
                "category_distribution": category_dist,
                "top_unresolved_terms": [
                    {
                        "term": r["term"],
                        "category": r["category"],
                        "frequency": r["frequency"],
                        "confidence": r["confidence"],
                    }
                    for r in top_terms_results
                ],
            }

        except Exception as e:
            logger.error(f"Failed to get ontology stats: {e}")
            return {
                "total_proposals": 0,
                "pending_count": 0,
                "approved_count": 0,
                "auto_approved_count": 0,
                "rejected_count": 0,
                "category_distribution": {},
                "top_unresolved_terms": [],
            }

    async def batch_update_proposal_status(
        self,
        proposal_ids: list[str],
        new_status: str,
        reviewed_by: str | None = None,
        rejection_reason: str | None = None,
    ) -> tuple[int, list[str]]:
        """일괄 상태 업데이트 (Optimistic Locking 없음)"""
        query = """
        UNWIND $proposal_ids as pid
        MATCH (p:OntologyProposal {id: pid})
        WHERE p.status = 'pending'
        SET
            p.status = $new_status,
            p.version = p.version + 1,
            p.reviewed_at = datetime(),
            p.reviewed_by = $reviewed_by,
            p.rejection_reason = $rejection_reason,
            p.updated_at = datetime()
        RETURN p.id as id
        """

        try:
            results = await self._client.execute_write(
                query,
                {
                    "proposal_ids": proposal_ids,
                    "new_status": new_status,
                    "reviewed_by": reviewed_by,
                    "rejection_reason": rejection_reason,
                },
            )

            updated_ids = {r["id"] for r in results}
            failed_ids = [pid for pid in proposal_ids if pid not in updated_ids]

            return len(updated_ids), failed_ids

        except Exception as e:
            logger.error(f"Failed to batch update proposals: {e}")
            return 0, proposal_ids

    async def update_proposal_with_version(
        self,
        proposal_id: str,
        expected_version: int,
        updates: dict[str, Any],
    ) -> OntologyProposal | None:
        """제안 수정 (Optimistic Locking)"""
        # SECURITY: 화이트리스트 기반 필드 검증
        allowed_fields = {
            "suggested_parent",
            "suggested_canonical",
            "category",
            "suggested_action",
            "status",
            "reviewed_at",
            "reviewed_by",
            "rejection_reason",
        }

        set_clauses = []
        params: dict[str, Any] = {
            "id": proposal_id,
            "expected_version": expected_version,
        }

        for field, value in updates.items():
            if field in allowed_fields:
                set_clauses.append(f"p.{field} = ${field}")
                params[field] = value

        if not set_clauses:
            return await self.get_proposal_by_id(proposal_id)

        set_clauses.extend(
            [
                "p.version = p.version + 1",
                "p.updated_at = datetime()",
            ]
        )

        query = f"""
        MATCH (p:OntologyProposal {{id: $id}})
        WHERE p.version = $expected_version
        SET {", ".join(set_clauses)}
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        """

        try:
            results = await self._client.execute_write(query, params)

            if results:
                return OntologyProposal.from_dict(results[0])
            return None

        except Exception as e:
            logger.error(f"Failed to update proposal {proposal_id}: {e}")
            return None

    async def create_proposal(
        self,
        proposal: OntologyProposal,
    ) -> OntologyProposal:
        """새 제안 생성 (수동 생성용)"""
        query = """
        CREATE (p:OntologyProposal {
            id: $id,
            version: 1,
            proposal_type: $proposal_type,
            term: $term,
            category: $category,
            suggested_action: $suggested_action,
            suggested_parent: $suggested_parent,
            suggested_canonical: $suggested_canonical,
            suggested_relation_type: $suggested_relation_type,
            evidence_questions: $evidence_questions,
            frequency: $frequency,
            confidence: $confidence,
            status: $status,
            source: $source,
            created_at: datetime(),
            updated_at: datetime(),
            reviewed_at: null,
            reviewed_by: null,
            rejection_reason: null,
            applied_at: null
        })
        RETURN
            p.id as id,
            p.version as version,
            p.proposal_type as proposal_type,
            p.term as term,
            p.category as category,
            p.suggested_action as suggested_action,
            p.suggested_parent as suggested_parent,
            p.suggested_canonical as suggested_canonical,
            p.suggested_relation_type as suggested_relation_type,
            p.evidence_questions as evidence_questions,
            p.frequency as frequency,
            p.confidence as confidence,
            p.status as status,
            p.source as source,
            p.created_at as created_at,
            p.updated_at as updated_at,
            p.reviewed_at as reviewed_at,
            p.reviewed_by as reviewed_by,
            p.rejection_reason as rejection_reason,
            p.applied_at as applied_at
        """

        data = proposal.to_dict()

        try:
            results = await self._client.execute_write(
                query,
                {
                    "id": data["id"],
                    "proposal_type": data["proposal_type"],
                    "term": data["term"],
                    "category": data["category"],
                    "suggested_action": data["suggested_action"],
                    "suggested_parent": data["suggested_parent"],
                    "suggested_canonical": data["suggested_canonical"],
                    "suggested_relation_type": data["suggested_relation_type"],
                    "evidence_questions": data["evidence_questions"],
                    "frequency": data["frequency"],
                    "confidence": data["confidence"],
                    "status": data["status"],
                    "source": data["source"],
                },
            )

            if results:
                return OntologyProposal.from_dict(results[0])
            return proposal

        except Exception as e:
            logger.error(f"Failed to create proposal: {e}")
            raise QueryExecutionError(
                f"Failed to create proposal: {e}", query=query
            ) from e

    async def get_proposal_current_version(self, proposal_id: str) -> int | None:
        """제안의 현재 버전 조회"""
        query = """
        MATCH (p:OntologyProposal {id: $id})
        RETURN p.version as version
        """

        try:
            results = await self._client.execute_query(query, {"id": proposal_id})

            if results:
                return results[0]["version"]
            return None

        except Exception as e:
            logger.error(f"Failed to get proposal version: {e}")
            return None

    async def update_proposal_applied_at(self, proposal_id: str) -> bool:
        """제안의 applied_at 필드 업데이트"""
        query = """
        MATCH (p:OntologyProposal {id: $id})
        SET p.applied_at = datetime()
        RETURN p.id as id
        """

        try:
            results = await self._client.execute_write(query, {"id": proposal_id})
            return len(results) > 0

        except Exception as e:
            logger.error(f"Failed to update proposal applied_at: {e}")
            return False
