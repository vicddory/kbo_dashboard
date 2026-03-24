"""
데이터 파싱/정제 모듈
- 문자열 → 숫자 변환
- 중복 선수 처리
- 데이터 품질 검증
"""

import re
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def create_dataframe(headers: list, rows: list) -> pd.DataFrame:
    """헤더와 행 데이터로 DataFrame을 생성한다."""
    if not headers or not rows:
        logger.warning("빈 데이터로 DataFrame 생성 시도")
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=headers)
    return df


def clean_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """문자열 컬럼의 공백, 특수문자를 정리한다."""
    str_cols = df.select_dtypes(include=["object"]).columns

    for col in str_cols:
        df[col] = df[col].str.strip()
        # 연속 공백을 단일 공백으로
        df[col] = df[col].str.replace(r"\s+", " ", regex=True)

    return df


def convert_numeric_columns(
    df: pd.DataFrame, exclude_cols: Optional[list] = None
) -> pd.DataFrame:
    """
    숫자로 변환 가능한 컬럼을 자동 감지하여 변환한다.
    Player_ID, 선수명, 팀명 등은 제외.
    """
    if exclude_cols is None:
        exclude_cols = ["Player_ID", "선수", "팀"]

    for col in df.columns:
        if col in exclude_cols:
            continue

        # 해당 컬럼의 값들이 숫자로 변환 가능한지 확인
        sample = df[col].dropna().head(20)
        if sample.empty:
            continue

        convertible = 0
        for val in sample:
            # '-', '', 빈 값은 숫자 변환 가능으로 취급
            val_str = str(val).strip()
            if val_str in ("-", "", "0"):
                convertible += 1
                continue
            # 숫자 패턴 매치 (음수, 소수점 포함)
            if re.match(r"^-?\d*\.?\d+$", val_str):
                convertible += 1

        # 80% 이상이 숫자면 변환
        if len(sample) > 0 and convertible / len(sample) >= 0.8:
            df[col] = df[col].replace("-", None).replace("", None)
            df[col] = pd.to_numeric(df[col], errors="coerce")
            logger.debug(f"숫자 변환 완료: {col}")

    return df


def handle_duplicate_players(df: pd.DataFrame) -> pd.DataFrame:
    """
    트레이드 등으로 중복 등장하는 선수를 처리한다.
    Player_ID 기준으로 중복 여부를 표시 (제거하지는 않음).
    """
    if "Player_ID" not in df.columns:
        return df

    # 빈 Player_ID 제외하고 중복 체크
    mask = df["Player_ID"] != ""
    duplicates = df.loc[mask, "Player_ID"].duplicated(keep=False)

    if duplicates.any():
        dup_count = df.loc[mask].loc[duplicates, "Player_ID"].nunique()
        logger.info(f"중복 선수 {dup_count}명 발견 (트레이드 등)")

    return df


def process_raw_data(
    headers: list,
    rows: list,
    category: str,
    year: Optional[int] = None,
) -> pd.DataFrame:
    """
    크롤링 원본 데이터를 정제된 DataFrame으로 변환하는 통합 파이프라인.

    1. DataFrame 생성
    2. 텍스트 정리
    3. 숫자 변환
    4. 중복 처리
    5. 메타데이터 추가 (카테고리, 연도)
    """
    logger.info(f"[{category}] 데이터 정제 시작 ({len(rows)}개 행)")

    # 1. DataFrame 생성
    df = create_dataframe(headers, rows)
    if df.empty:
        return df

    # 2. 텍스트 정리
    df = clean_text_columns(df)

    # 3. 숫자 변환
    df = convert_numeric_columns(df)

    # 4. 중복 처리
    df = handle_duplicate_players(df)

    # 5. 메타데이터 추가
    df["_category"] = category
    if year:
        df["_year"] = year

    logger.info(
        f"[{category}] 데이터 정제 완료 — "
        f"{len(df)}행 × {len(df.columns)}열, "
        f"숫자 컬럼 {len(df.select_dtypes(include='number').columns)}개"
    )

    return df
