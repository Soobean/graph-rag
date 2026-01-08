"""
Graph Layer Utilities

LangGraph 노드에서 공용으로 사용하는 유틸리티 함수
"""

from langchain_core.messages import BaseMessage


def format_chat_history(
    messages: list[BaseMessage],
    exclude_last: bool = True,
) -> str:
    """
    LangChain 메시지 리스트를 LLM 프롬프트용 문자열로 변환

    Args:
        messages: BaseMessage 리스트 (HumanMessage, AIMessage 등)
        exclude_last: True이면 마지막 메시지 제외 (기본값: True)
                     파이프라인에서 현재 질문이 별도로 전달되므로 중복 방지를 위해 사용

    Returns:
        포맷된 대화 기록 문자열 (대화 없으면 빈 문자열)

    Example:
        >>> messages = [HumanMessage("안녕"), AIMessage("안녕하세요!"), HumanMessage("질문")]
        >>> format_chat_history(messages)  # exclude_last=True (기본값)
        'User: 안녕\\nAssistant: 안녕하세요!'
        >>> format_chat_history(messages, exclude_last=False)
        'User: 안녕\\nAssistant: 안녕하세요!\\nUser: 질문'
    """
    if not messages:
        return ""

    # 마지막 메시지 제외 여부 결정
    target_messages = messages[:-1] if exclude_last and len(messages) > 1 else messages

    if not target_messages:
        return ""

    lines = []
    for msg in target_messages:
        role = "User" if msg.type == "human" else "Assistant"
        lines.append(f"{role}: {msg.content}")

    return "\n".join(lines)
