"""
저장소 모듈
- BaseStorage: 저장소 인터페이스 (확장 포인트)
- SQLiteStorage: SQLite 구현
- CSVStorage: CSV 구현 (백업/공유용)
"""

import os
import sqlite3
import logging
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from kbo_config import SQLITE_DB_PATH, CSV_OUTPUT_DIR

logger = logging.getLogger(__name__)


# ============================================================
# 저장소 인터페이스 (확장 포인트)
# ============================================================
class BaseStorage(ABC):
    """
    저장소 베이스 클래스.
    PostgreSQL, MongoDB 등으로 교체하려면 이 클래스를 상속.

    확장 예시:
        class PostgresStorage(BaseStorage):
            def save(self, df, table_name, **kwargs):
                ...
            def load(self, table_name, **kwargs):
                ...
    """

    @abstractmethod
    def save(self, df: pd.DataFrame, table_name: str, **kwargs) -> bool:
        pass

    @abstractmethod
    def load(self, table_name: str, **kwargs) -> pd.DataFrame:
        pass

    @abstractmethod
    def close(self):
        pass


# ============================================================
# SQLite 저장소
# ============================================================
class SQLiteStorage(BaseStorage):
    """
    SQLite 기반 저장소.
    Player_ID를 기준으로 조인이 가능한 통합 DB.
    """

    def __init__(self, db_path: str = SQLITE_DB_PATH):
        self.db_path = db_path
        self.conn = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self._connect()

    def _connect(self):
        """DB 연결"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.logger.info(f"SQLite 연결 완료: {self.db_path}")
        except sqlite3.Error as e:
            self.logger.error(f"SQLite 연결 실패: {e}")
            raise

    def save(
        self,
        df: pd.DataFrame,
        table_name: str,
        if_exists: str = "replace",
        **kwargs,
    ) -> bool:
        """
        DataFrame을 SQLite 테이블로 저장한다.

        Args:
            df: 저장할 데이터
            table_name: 테이블 이름
            if_exists: 'replace' | 'append' | 'fail'
        """
        if df.empty:
            self.logger.warning(f"빈 DataFrame, 저장 스킵: {table_name}")
            return False

        try:
            df.to_sql(table_name, self.conn, if_exists=if_exists, index=False)
            self.logger.info(
                f"SQLite 저장 완료: {table_name} ({len(df)}행)"
            )
            return True
        except Exception as e:
            self.logger.error(f"SQLite 저장 실패 ({table_name}): {e}")
            return False

    def load(
        self, table_name: str, where: Optional[str] = None, **kwargs
    ) -> pd.DataFrame:
        """
        SQLite 테이블에서 데이터를 읽는다.

        Args:
            table_name: 테이블 이름
            where: WHERE 절 (예: "Player_ID = '12345'")
        """
        try:
            query = f"SELECT * FROM {table_name}"
            if where:
                query += f" WHERE {where}"
            df = pd.read_sql_query(query, self.conn)
            self.logger.info(
                f"SQLite 로드 완료: {table_name} ({len(df)}행)"
            )
            return df
        except Exception as e:
            self.logger.error(f"SQLite 로드 실패 ({table_name}): {e}")
            return pd.DataFrame()

    def list_tables(self) -> list:
        """저장된 테이블 목록을 반환한다."""
        try:
            cursor = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"테이블 목록 조회 실패: {e}")
            return []

    def execute_query(self, query: str) -> pd.DataFrame:
        """
        임의 SQL 쿼리를 실행한다.
        WPA 계산, FA 적정가 산출 등에서 조인 쿼리 사용 시 활용.
        """
        try:
            return pd.read_sql_query(query, self.conn)
        except Exception as e:
            self.logger.error(f"쿼리 실행 실패: {e}")
            return pd.DataFrame()

    def close(self):
        """DB 연결 종료"""
        if self.conn:
            self.conn.close()
            self.logger.info("SQLite 연결 종료")


# ============================================================
# CSV 저장소 (백업/공유용)
# ============================================================
class CSVStorage(BaseStorage):
    """
    CSV 파일 기반 저장소.
    데이터 공유나 백업 용도로 사용.
    """

    def __init__(self, output_dir: str = CSV_OUTPUT_DIR):
        self.output_dir = output_dir
        self.logger = logging.getLogger(self.__class__.__name__)
        os.makedirs(self.output_dir, exist_ok=True)

    def save(self, df: pd.DataFrame, table_name: str, **kwargs) -> bool:
        """DataFrame을 CSV로 저장한다."""
        if df.empty:
            self.logger.warning(f"빈 DataFrame, 저장 스킵: {table_name}")
            return False

        filepath = os.path.join(self.output_dir, f"{table_name}.csv")
        try:
            df.to_csv(filepath, index=False, encoding="utf-8-sig")
            self.logger.info(f"CSV 저장 완료: {filepath} ({len(df)}행)")
            return True
        except Exception as e:
            self.logger.error(f"CSV 저장 실패 ({filepath}): {e}")
            return False

    def load(self, table_name: str, **kwargs) -> pd.DataFrame:
        """CSV에서 데이터를 읽는다."""
        filepath = os.path.join(self.output_dir, f"{table_name}.csv")
        try:
            df = pd.read_csv(filepath, encoding="utf-8-sig")
            self.logger.info(f"CSV 로드 완료: {filepath} ({len(df)}행)")
            return df
        except Exception as e:
            self.logger.error(f"CSV 로드 실패 ({filepath}): {e}")
            return pd.DataFrame()

    def close(self):
        """CSV는 별도 종료 불필요"""
        pass
