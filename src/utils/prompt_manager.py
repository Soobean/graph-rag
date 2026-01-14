"""
프롬프트 매니저

외부 YAML 파일에서 프롬프트 템플릿을 로드하고 관리합니다.
"""

import logging
from pathlib import Path
from typing import cast

import yaml

from src.domain.types import PromptTemplate

logger = logging.getLogger(__name__)

# 프로젝트 루트 기준 prompts 디렉토리 (src/utils/prompt_manager.py 기준 두 단계 상위)
DEFAULT_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class PromptManager:
    """프롬프트 템플릿 관리자"""

    def __init__(self, prompts_dir: str | Path | None = None):
        """
        초기화

        Args:
            prompts_dir: 프롬프트 파일이 위치한 디렉토리 경로 (기본: src/prompts)
        """
        if prompts_dir is None:
            self._prompts_dir = DEFAULT_PROMPTS_DIR
        elif isinstance(prompts_dir, str):
            self._prompts_dir = Path(prompts_dir)
        else:
            self._prompts_dir = prompts_dir

        self._cache: dict[str, PromptTemplate] = {}
        logger.info(f"PromptManager initialized with dir: {self._prompts_dir}")

    def load_prompt(self, prompt_name: str, use_cache: bool = True) -> PromptTemplate:
        """
        프롬프트 로드

        Args:
            prompt_name: 프롬프트 파일 이름 (확장자 제외, 예: "intent_classification")
            use_cache: 캐시 사용 여부

        Returns:
            PromptTemplate: {"system": ..., "user": ...}

        Raises:
            FileNotFoundError: 파일이 없을 경우
            ValueError: YAML 형식이 올바르지 않을 경우
        """
        if use_cache and prompt_name in self._cache:
            return self._cache[prompt_name]

        file_path = self._prompts_dir / f"{prompt_name}.yaml"

        try:
            if not file_path.exists():
                raise FileNotFoundError(f"Prompt file not found: {file_path}")

            with open(file_path, encoding="utf-8") as f:
                content = yaml.safe_load(f)

            if not isinstance(content, dict):
                raise ValueError(f"Prompt content must be a dictionary: {file_path}")

            # 타입 캐스팅 및 검증
            # 기본적으로 system, user 키가 필요하나 여기서는 단순 dict 체크만 우선 하고
            # TypedDict로 캐스팅. 실제 사용처에서 키 에러가 나면 발견됨.
            prompt_template = cast(PromptTemplate, content)

            if use_cache:
                self._cache[prompt_name] = prompt_template

            return prompt_template

        except Exception as e:
            logger.error(f"Failed to load prompt '{prompt_name}': {e}")
            raise
