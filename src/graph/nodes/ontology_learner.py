"""
Ontology Learner - 온톨로지 자동 학습 서비스

미해결 엔티티를 LLM으로 분석하여 온톨로지 변경 제안을 생성합니다.

핵심 기능:
- 미해결 엔티티 분석 (LLM 기반)
- 온톨로지 변경 제안 생성 (NEW_CONCEPT, NEW_SYNONYM, NEW_RELATION)
- 자동 승인 조건 평가 및 적용
- Neo4j에 제안 저장

사용 패턴:
- 백그라운드 프로세서로 실행 (fire-and-forget)
- 메인 파이프라인 성능에 영향 없음
- 실패 시 로그만 남기고 스킵 (graceful degradation)
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import unicodedata
from typing import TYPE_CHECKING, Any

from src.config import AdaptiveOntologySettings
from src.domain.adaptive.models import (
    OntologyProposal,
    ProposalStatus,
    ProposalType,
)
from src.domain.types import UnresolvedEntity
from src.repositories.llm_repository import LLMRepository, ModelTier
from src.utils.prompt_manager import PromptManager

if TYPE_CHECKING:
    from src.domain.ontology.hybrid_loader import HybridOntologyLoader
    from src.domain.ontology.loader import OntologyLoader
    from src.repositories.neo4j_repository import Neo4jRepository

logger = logging.getLogger(__name__)


class OntologyLearner:
    """
    온톨로지 자동 학습 서비스

    EntityResolver에서 발견된 미해결 엔티티를 분석하여
    온톨로지 변경 제안(OntologyProposal)을 생성합니다.

    Usage:
        learner = OntologyLearner(
            settings=settings.adaptive_ontology,
            llm_repository=llm_repo,
            neo4j_repository=neo4j_repo,
            ontology_loader=ontology_loader,
        )

        # 비동기 백그라운드 실행
        asyncio.create_task(
            learner.process_unresolved(unresolved_entities, current_schema)
        )
    """

    def __init__(
        self,
        settings: AdaptiveOntologySettings,
        llm_repository: LLMRepository,
        neo4j_repository: Neo4jRepository,
        ontology_loader: OntologyLoader | HybridOntologyLoader | None = None,
    ):
        """
        Args:
            settings: Adaptive Ontology 설정
            llm_repository: LLM API 접근 레포지토리
            neo4j_repository: Neo4j 접근 레포지토리
            ontology_loader: 현재 온톨로지 로더 (컨텍스트 제공용)
        """
        self._settings = settings
        self._llm = llm_repository
        self._neo4j = neo4j_repository
        self._ontology = ontology_loader
        self._prompt_manager = PromptManager()

        logger.info(
            f"OntologyLearner initialized "
            f"(enabled={settings.enabled}, auto_approve={settings.auto_approve_enabled})"
        )

    @property
    def is_enabled(self) -> bool:
        """기능 활성화 여부"""
        return self._settings.enabled

    def validate_term(self, term: str) -> bool:
        """
        용어 유효성 검증

        Args:
            term: 검증할 용어

        Returns:
            유효성 여부
        """
        if not term or not term.strip():
            return False

        # Unicode 정규화 (NFC) - 동일 문자의 다른 표현 통일
        term = unicodedata.normalize("NFC", term.strip())

        # 길이 검증
        if len(term) < self._settings.min_term_length:
            return False
        if len(term) > self._settings.max_term_length:
            return False

        # 순수 숫자 또는 특수문자만 있는 경우 제외
        if term.isdigit():
            return False

        # 최소 하나의 문자(한글/영문) 포함 확인
        has_letter = any(c.isalpha() for c in term)
        if not has_letter:
            return False

        return True

    async def process_unresolved(
        self,
        unresolved: list[UnresolvedEntity],
        current_schema: dict[str, Any] | None = None,
    ) -> list[OntologyProposal]:
        """
        미해결 엔티티 분석 및 제안 생성

        Args:
            unresolved: 미해결 엔티티 리스트
            current_schema: 현재 그래프 스키마 (컨텍스트용)

        Returns:
            생성된 OntologyProposal 리스트
        """
        if not self.is_enabled:
            logger.debug("OntologyLearner is disabled")
            return []

        if not unresolved:
            return []

        # 유효한 엔티티만 필터링
        valid_unresolved = [
            u for u in unresolved if self.validate_term(u.get("term", ""))
        ]

        if not valid_unresolved:
            logger.info("No valid unresolved entities to process")
            return []

        logger.info(f"Processing {len(valid_unresolved)} unresolved entities")

        proposals: list[OntologyProposal] = []

        for item in valid_unresolved:
            try:
                proposal = await self._process_single_entity(item, current_schema)
                if proposal:
                    proposals.append(proposal)
            except Exception as e:
                logger.warning(
                    f"Failed to process entity '{item.get('term')}': {e}"
                )
                continue

        logger.info(f"Generated {len(proposals)} ontology proposals")
        return proposals

    async def _process_single_entity(
        self,
        entity: UnresolvedEntity,
        current_schema: dict[str, Any] | None = None,
    ) -> OntologyProposal | None:
        """
        단일 미해결 엔티티 처리

        1. 기존 제안 확인 → 빈도 증가
        2. LLM 분석 → 새 제안 생성
        3. 자동 승인 조건 확인
        4. Neo4j 저장

        Args:
            entity: 미해결 엔티티
            current_schema: 현재 그래프 스키마

        Returns:
            생성/업데이트된 OntologyProposal 또는 None
        """
        term = entity.get("term", "").strip()
        category = entity.get("category", "skills")
        question = entity.get("question", "")

        # 1. 기존 제안 확인
        existing = await self._neo4j.find_ontology_proposal(term, category)

        if existing:
            # 빈도 증가 및 증거 추가
            await self._neo4j.update_proposal_frequency(existing.id, question)
            existing.add_evidence(question)

            # 자동 승인 조건 재평가 (빈도 증가 후)
            await self._check_and_auto_approve(existing)

            logger.debug(f"Updated existing proposal for '{term}' (freq={existing.frequency})")
            return existing

        # 2. LLM 분석으로 새 제안 생성
        analysis = await self._analyze_with_llm(term, category, question)

        if not analysis:
            logger.debug(f"LLM analysis returned no result for '{term}'")
            return None

        # 3. OntologyProposal 생성
        proposal_type = self._parse_proposal_type(analysis.get("type", ""))
        if not proposal_type:
            logger.warning(f"Invalid proposal type from LLM: {analysis.get('type')}")
            return None

        # confidence 값 파싱 및 범위 검증 (0.0 ~ 1.0)
        try:
            raw_confidence = float(analysis.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, raw_confidence))  # Clamp to valid range
            if raw_confidence != confidence:
                logger.warning(
                    f"Confidence value {raw_confidence} clamped to {confidence}"
                )
        except (ValueError, TypeError):
            logger.warning(f"Invalid confidence value: {analysis.get('confidence')}")
            confidence = 0.0

        proposal = OntologyProposal(
            proposal_type=proposal_type,
            term=term,
            category=category,
            suggested_action=analysis.get("action", ""),
            suggested_parent=analysis.get("parent"),
            suggested_canonical=analysis.get("canonical"),
            evidence_questions=[question] if question else [],
            frequency=1,
            confidence=confidence,
        )

        # 4. Neo4j 저장
        saved_proposal = await self._neo4j.save_ontology_proposal(proposal)

        # 5. 자동 승인 조건 확인
        await self._check_and_auto_approve(saved_proposal)

        logger.info(
            f"Created proposal for '{term}': type={proposal_type.value}, "
            f"confidence={saved_proposal.confidence:.2f}"
        )

        return saved_proposal

    async def _analyze_with_llm(
        self,
        term: str,
        category: str,
        question: str,
    ) -> dict[str, Any] | None:
        """
        LLM으로 미해결 용어 분석

        Args:
            term: 분석할 용어
            category: 카테고리
            question: 원본 질문

        Returns:
            분석 결과 딕셔너리 또는 None
        """
        try:
            prompt = self._prompt_manager.load_prompt("ontology_analysis")

            # 현재 온톨로지의 기존 개념 목록 생성
            category_concepts = self._get_category_concepts(category)

            system_prompt = prompt["system"].format(
                category_concepts=category_concepts,
            )
            user_prompt = prompt["user"].format(
                term=term,
                category=category,
                question=question,
            )

            # Light 모델로 분석 (빠른 처리 우선)
            result = await asyncio.wait_for(
                self._llm.generate_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model_tier=ModelTier.LIGHT,
                ),
                timeout=self._settings.analysis_timeout_seconds,
            )

            return result

        except TimeoutError:
            logger.warning(f"LLM analysis timed out for '{term}'")
            return None
        except Exception as e:
            logger.error(f"LLM analysis failed for '{term}': {e}")
            return None

    def _get_category_concepts(self, category: str) -> str:
        """
        카테고리의 기존 개념 목록을 문자열로 반환

        Args:
            category: 카테고리명

        Returns:
            기존 개념 목록 (줄바꿈으로 구분)
        """
        if self._ontology is None:
            return "(온톨로지 정보 없음)"

        try:
            # OntologyLoader 또는 HybridOntologyLoader의 내부 YAML 로더 접근
            yaml_loader = self._get_yaml_loader()
            if yaml_loader is None:
                return "(YAML 온톨로지 정보 없음)"

            # 스킬 카테고리인 경우 schema에서 모든 스킬 추출
            if category == "skills":
                schema = yaml_loader.load_schema()
                concepts = schema.get("concepts", {})
                skill_categories = concepts.get("SkillCategory", [])

                skills: list[str] = []
                for cat in skill_categories:
                    if isinstance(cat, dict):
                        skills.extend(cat.get("skills", []))
                        for sub in cat.get("subcategories", []):
                            skills.extend(sub.get("skills", []))

                if skills:
                    # islice로 효율적 제한 후 리스트화 (중첩 iteration 방지)
                    skills_limited = list(itertools.islice(skills, 50))
                    return "\n".join(f"- {s}" for s in skills_limited)

            # 동의어에서 canonical 목록 추출
            synonyms = yaml_loader.load_synonyms()
            category_data = synonyms.get(category, {})

            canonicals: list[str] = []
            for _key, info in category_data.items():
                if isinstance(info, dict):
                    canonical = info.get("canonical", _key)
                    if canonical not in canonicals:
                        canonicals.append(canonical)
                        # 50개 도달 시 조기 종료
                        if len(canonicals) >= 50:
                            break

            if canonicals:
                return "\n".join(f"- {c}" for c in canonicals)

            return "(카테고리에 등록된 개념 없음)"

        except Exception as e:
            logger.warning(f"Failed to get category concepts for '{category}': {e}")
            return ""

    def _get_yaml_loader(self) -> OntologyLoader | None:
        """
        YAML 기반 OntologyLoader 인스턴스 반환

        HybridOntologyLoader인 경우 내부 _yaml_loader를 반환합니다.

        Returns:
            OntologyLoader 인스턴스 또는 None
        """
        from src.domain.ontology.loader import OntologyLoader

        if self._ontology is None:
            return None

        # OntologyLoader인 경우 직접 반환
        if isinstance(self._ontology, OntologyLoader):
            return self._ontology

        # HybridOntologyLoader인 경우 내부 _yaml_loader 반환
        yaml_loader = getattr(self._ontology, "_yaml_loader", None)
        if isinstance(yaml_loader, OntologyLoader):
            return yaml_loader

        return None

    def _parse_proposal_type(self, type_str: str) -> ProposalType | None:
        """
        문자열을 ProposalType enum으로 변환 (LLM 응답 유연하게 파싱)

        Args:
            type_str: "NEW_CONCEPT", "new concept", "new_synonym" 등

        Returns:
            ProposalType 또는 None
        """
        # 정규화: 대문자 + 공백을 언더스코어로 변환
        normalized = type_str.upper().strip().replace(" ", "_")

        type_map = {
            "NEW_CONCEPT": ProposalType.NEW_CONCEPT,
            "NEW_SYNONYM": ProposalType.NEW_SYNONYM,
            "NEW_RELATION": ProposalType.NEW_RELATION,
            # LLM이 다른 형식으로 응답할 경우 대비
            "CONCEPT": ProposalType.NEW_CONCEPT,
            "SYNONYM": ProposalType.NEW_SYNONYM,
            "RELATION": ProposalType.NEW_RELATION,
        }

        return type_map.get(normalized)

    async def _check_and_auto_approve(
        self,
        proposal: OntologyProposal,
    ) -> bool:
        """
        자동 승인 조건 확인 및 적용

        Args:
            proposal: 확인할 제안

        Returns:
            자동 승인 적용 여부
        """
        if not self._settings.auto_approve_enabled:
            return False

        if proposal.status != ProposalStatus.PENDING:
            return False

        # 허용 타입 확인
        allowed_types = [
            ProposalType(t) for t in self._settings.auto_approve_types
            if t in [pt.value for pt in ProposalType]
        ]

        # 자동 승인 조건 체크
        if not proposal.can_auto_approve(
            min_confidence=self._settings.auto_approve_confidence,
            min_frequency=self._settings.auto_approve_min_frequency,
            allowed_types=allowed_types,
        ):
            return False

        # 원자적 자동 승인 (일일 한도 + Optimistic Locking 동시 처리)
        success = await self._neo4j.try_auto_approve_with_limit(
            proposal_id=proposal.id,
            expected_version=proposal.version,
            daily_limit=self._settings.auto_approve_daily_limit,
        )

        if success:
            # 로컬 상태도 업데이트
            proposal.approve(auto=True)
            logger.info(
                f"Auto-approved proposal: '{proposal.term}' "
                f"(type={proposal.proposal_type.value}, freq={proposal.frequency})"
            )
        else:
            logger.debug(
                f"Auto-approve skipped for '{proposal.term}': "
                "limit reached or concurrent modification"
            )

        return success
