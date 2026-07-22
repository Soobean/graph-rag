"""
LLM Faithfulness Judge

응답이 실제 graph_results의 (subject, relation, object) 페어에 충실한지 채점.
과거 "페어 손실" 버그(서로 다른 행의 값을 한 인물에게 잘못 합침)의 재발을
감지하는 것이 핵심 목적이다.

제품 코드(src/)를 오염하지 않기 위해 LLMTaskService에 메서드를 추가하지 않고,
AzureOpenAIGateway primitive를 직접 호출한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evals.models import JudgeResult
from src.application.llm.formatters import format_results
from src.infrastructure.llm import AzureOpenAIGateway, ModelTier
from src.utils.prompt_manager import PromptManager

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_prompt_manager = PromptManager(prompts_dir=_PROMPTS_DIR)

# judge 입력이 과대해지지 않도록 결과 행 수 제한 (format_results 내부 상한과 별개)
MAX_JUDGE_ROWS = 60


async def judge_faithfulness(
    gateway: AzureOpenAIGateway,
    *,
    question: str,
    response: str,
    graph_results: list[dict[str, Any]],
) -> JudgeResult:
    """응답 충실성 채점 (LIGHT 티어 1회 호출)"""
    prompt = _prompt_manager.load_prompt("eval_judge")

    # 페어 보존 포맷 재사용 — 응답 생성 LLM이 받은 것과 같은 표현으로 대조
    formatted = format_results(graph_results[:MAX_JUDGE_ROWS])

    result = await gateway.generate_json(
        system_prompt=prompt["system"],
        user_prompt=prompt["user"].format(
            question=question,
            total_rows=len(graph_results),
            max_rows=MAX_JUDGE_ROWS,
            formatted_results=formatted,
            response=response,
        ),
        model_tier=ModelTier.LIGHT,
    )

    return JudgeResult(
        faithful=bool(result.get("faithful", False)),
        score=float(result.get("score", 0.0)),
        violations=[
            {
                "claim": str(v.get("claim", "")),
                "reason": str(v.get("reason", "")),
            }
            for v in result.get("violations", [])
            if isinstance(v, dict)
        ],
    )
