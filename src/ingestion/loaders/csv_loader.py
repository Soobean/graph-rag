"""
CSV Data Loader Implementation

CSV 파일을 읽어 Document 객체로 변환하는 로더 구현체입니다.
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from src.ingestion.loaders.base import BaseLoader
from src.ingestion.models import Document


class CSVLoader(BaseLoader):
    """
    CSV 파일 로더

    특정 디렉토리 내의 CSV 파일들을 읽어서
    각 행(Row)을 텍스트로 변환하여 Document 객체 생성
    """

    def __init__(self, file_path: str | Path, encoding: str = "utf-8") -> None:
        self.file_path = Path(file_path)
        self.encoding = encoding

    def load(self) -> Iterator[Document]:
        """CSV 파일을 읽어 Document 스트림 반환"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        # 파일명 기반으로 "데이터 타입" 추론 (예: employees.csv -> employees)
        source_name = self.file_path.stem

        with open(self.file_path, encoding=self.encoding) as f:
            reader = csv.DictReader(f)

            for i, row in enumerate(reader):
                # CSV Row를 텍스트로 변환 (Context Serialization)
                # 예: "name: John, job: Developer"
                # Note: None과 빈 문자열만 제외, 숫자 0은 유효한 값으로 포함
                content_parts = [
                    f"{k}: {v}"
                    for k, v in row.items()
                    if v is not None and str(v).strip()
                ]
                page_content = ", ".join(content_parts)

                # 메타데이터 생성 (Lineage용)
                metadata = {
                    "source": str(self.file_path.name),
                    "row_index": i + 2,  # Header 제외 1-based index
                    "source_type": source_name,
                }

                yield Document(page_content=page_content, metadata=metadata)
