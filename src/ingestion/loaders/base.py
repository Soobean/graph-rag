"""
Data Loader Interface (Adapter Pattern)

모든 데이터 소스 로더가 구현해야 할 추상 기본 클래스입니다.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator

from src.ingestion.models import Document


class BaseLoader(ABC):
    """
    데이터 로더 추상 클래스

    데이터 소스(CSV, DB, JSON 등)에 관계없이
    항상 표준 Document 객체의 Iterator를 반환해야 합니다.
    """

    @abstractmethod
    def load(self) -> Iterator[Document]:
        """
        데이터 소스에서 데이터를 읽어 Document 객체로 변환하여 반환
        """
        pass
