"""Checkpointer 팩토리.

설정에 따라 SQLite 영속 또는 MemorySaver를 반환합니다.
"""

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


async def create_checkpointer(db_path: str = ":memory:") -> BaseCheckpointSaver:
    """Checkpointer 인스턴스 생성.

    Args:
        db_path: SQLite DB 경로. ':memory:'면 MemorySaver 사용.
    """
    if db_path == ":memory:":
        return MemorySaver()

    try:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        conn = await aiosqlite.connect(db_path)
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        logger.info(f"AsyncSqliteSaver ready (path={db_path})")
        return saver
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-sqlite not installed, falling back to MemorySaver. "
            "Install with: uv add langgraph-checkpoint-sqlite"
        )
        return MemorySaver()
