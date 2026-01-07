"""
Excel Data Loader Implementation

Excel 파일(.xlsx, .xls)을 읽어 Document 객체로 변환하는 로더 구현체입니다.
"""

from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from src.ingestion.loaders.base import BaseLoader
from src.ingestion.models import Document


class ExcelLoader(BaseLoader):
    """
    Excel 파일 로더

    Excel 파일(.xlsx, .xls)을 읽어서
    각 행(Row)을 텍스트로 변환하여 Document 객체 생성
    """

    def __init__(
        self,
        file_path: str | Path,
        sheet_name: str | int = 0,
        header_row: int = 0,
        usecols: list[int] | None = None,
    ) -> None:
        """
        Args:
            file_path: Excel 파일 경로
            sheet_name: 읽을 시트 이름 또는 인덱스 (기본: 첫 번째 시트)
            header_row: 헤더 행 인덱스 (0-based)
            usecols: 사용할 컬럼 인덱스 리스트 (None이면 모든 컬럼)
        """
        self.file_path = Path(file_path)
        self.sheet_name = sheet_name
        self.header_row = header_row
        self.usecols = usecols

    def load(self) -> Iterator[Document]:
        """Excel 파일을 읽어 Document 스트림 반환"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        # 파일명 기반으로 "데이터 타입" 추론
        source_name = self.file_path.stem

        # Excel 파일 읽기
        try:
            df = pd.read_excel(
                self.file_path,
                sheet_name=self.sheet_name,
                header=self.header_row,
                usecols=self.usecols,
                engine="openpyxl",  # .xlsx 파일용
            )
        except Exception as e:
            raise ValueError(f"Failed to read Excel file {self.file_path}: {e}") from e

        # NaN을 None으로 변환
        df = df.where(pd.notna(df), None)

        # 컬럼명 정리 (공백 제거)
        clean_columns = []
        for i, col in enumerate(df.columns):
            col_str = str(col).strip()
            # Unnamed 또는 빈 컬럼 처리
            if col_str.startswith("Unnamed") or not col_str:
                clean_columns.append(f"col_{i}")
            else:
                clean_columns.append(col_str)
        df.columns = clean_columns

        # Unnamed/빈 컬럼 제거 (col_로 시작하는 컬럼)
        valid_columns = [col for col in df.columns if not col.startswith("col_")]
        if valid_columns:
            df = df[valid_columns]

        for i, row in df.iterrows():
            # Excel Row를 텍스트로 변환 (Context Serialization)
            # None, NaN, 빈 문자열만 제외, 숫자 0은 유효한 값으로 포함
            content_parts = []
            for k, v in row.items():
                if v is not None and pd.notna(v):
                    str_v = str(v).strip()
                    if str_v and str_v.lower() != "nan":
                        content_parts.append(f"{k}: {str_v}")

            # 빈 행은 건너뛰기
            if not content_parts:
                continue

            page_content = ", ".join(content_parts)

            # 메타데이터 생성 (Lineage용)
            # Excel 행 번호 = header_row + data_row_index + 2 (1-based, header 포함)
            metadata = {
                "source": str(self.file_path.name),
                "row_index": int(i) + self.header_row + 2,
                "source_type": source_name,
                "sheet_name": str(self.sheet_name),
            }

            yield Document(page_content=page_content, metadata=metadata)
