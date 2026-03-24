"""
wRC+ 계산 모듈 (FanGraphs 방식)

타자의 종합 공격 가치를 리그 평균 및 파크팩터로 보정하여 비교 가능한 지표로 변환.
100이 리그 평균, 100 이상이면 평균보다 우수.

계산 흐름:
    1. wOBA 계산 (각 타격 이벤트에 득점 가치 가중치 부여)
    2. wRAA 계산 (wOBA 기반 평균 대비 득점 기여도)
    3. 파크팩터 보정
    4. 리그 평균으로 나누어 wRC+ 도출

공식 (FanGraphs):
    wRC+ = (((wRAA/PA + lgR/PA) + (lgR/PA - PF × lgR/PA))
            / (AL or NL wRC/PA)) × 100

    KBO는 DH 리그이므로 투수 타석 제외 불필요.
    lgR/PA = 리그 총득점 / 리그 총타석

참고:
    - FanGraphs Library: wRC and wRC+
      (https://library.fangraphs.com/offense/wrc/)
    - FanGraphs Blog: wRC and wRAA (David Appelman, 2008)
      (https://blogs.fangraphs.com/wrc-and-wraa/)
    - MLB.com Glossary: wRC+
      (https://www.mlb.com/glossary/advanced-stats/weighted-runs-created-plus)
"""

import logging
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# wOBA 가중치 (KBO용 기본값)
# ============================================================
# MLB FanGraphs의 연도별 가중치를 참고하되,
# KBO 득점 환경에 맞춰 조정 필요. 아래는 시작점으로 사용할 기본값.
# 추후 리그 데이터로 자체 산출 가능 (Linear Weights 기반).

DEFAULT_WOBA_WEIGHTS = {
    "BB": 0.69,      # 볼넷 (고의사구 제외)
    "HBP": 0.72,     # 사구
    "1B": 0.88,      # 단타
    "2B": 1.24,      # 2루타
    "3B": 1.56,      # 3루타
    "HR": 2.01,      # 홈런
}

# wOBA 스케일: wOBA를 득점 단위로 변환하는 계수
# 대략 OBP 스케일과 wOBA 스케일의 비율 (보통 ~1.15)
DEFAULT_WOBA_SCALE = 1.15


def calculate_woba(
    bb: int,
    hbp: int,
    singles: int,
    doubles: int,
    triples: int,
    hr: int,
    ab: int,
    sf: int = 0,
    ibb: int = 0,
    weights: Optional[dict] = None,
) -> Optional[float]:
    """
    개별 타자의 wOBA를 계산한다.

    공식:
        wOBA = (wBB×(BB-IBB) + wHBP×HBP + w1B×1B + w2B×2B + w3B×3B + wHR×HR)
               / (AB + BB - IBB + SF + HBP)

    Args:
        bb: 볼넷 (고의사구 포함 전체)
        hbp: 사구
        singles: 단타
        doubles: 2루타
        triples: 3루타
        hr: 홈런
        ab: 타수
        sf: 희생플라이
        ibb: 고의사구
        weights: wOBA 가중치 딕셔너리 (None이면 기본값)

    Returns:
        wOBA 값 (None if 분모가 0)
    """
    w = weights or DEFAULT_WOBA_WEIGHTS

    denominator = ab + (bb - ibb) + sf + hbp
    if denominator <= 0:
        return None

    numerator = (
        w["BB"] * (bb - ibb)
        + w["HBP"] * hbp
        + w["1B"] * singles
        + w["2B"] * doubles
        + w["3B"] * triples
        + w["HR"] * hr
    )

    return round(numerator / denominator, 4)


def calculate_wraa(
    woba: float,
    lg_woba: float,
    pa: int,
    woba_scale: float = DEFAULT_WOBA_SCALE,
) -> float:
    """
    wRAA (Weighted Runs Above Average)를 계산한다.

    공식:
        wRAA = ((wOBA - lgwOBA) / wOBAScale) × PA

    Args:
        woba: 선수의 wOBA
        lg_woba: 리그 평균 wOBA
        pa: 타석 수
        woba_scale: wOBA 스케일 계수

    Returns:
        wRAA 값 (양수 = 평균 이상, 음수 = 평균 이하)
    """
    if woba_scale <= 0:
        return 0.0

    return round(((woba - lg_woba) / woba_scale) * pa, 2)


def calculate_wrc_plus(
    wraa: float,
    pa: int,
    lg_r_per_pa: float,
    park_factor: float = 1.0,
    lg_wrc_per_pa: Optional[float] = None,
) -> Optional[float]:
    """
    개별 타자의 wRC+를 계산한다.

    FanGraphs 공식:
        wRC+ = (((wRAA/PA + lgR/PA) + (lgR/PA - PF × lgR/PA))
                / lgWRC/PA) × 100

    KBO는 DH 리그이므로 lgWRC/PA ≈ lgR/PA 로 근사 가능.

    Args:
        wraa: 선수의 wRAA
        pa: 타석 수
        lg_r_per_pa: 리그 평균 타석당 득점
        park_factor: 해당 선수 홈구장의 파크팩터
        lg_wrc_per_pa: 리그 평균 타석당 wRC (None이면 lgR/PA 사용)

    Returns:
        wRC+ 값 (None if 계산 불가)
    """
    if pa <= 0 or lg_r_per_pa <= 0:
        return None

    # KBO는 DH 리그 → 투수 타석 제외 불필요
    # lgWRC/PA는 lgR/PA로 근사
    denominator = lg_wrc_per_pa if lg_wrc_per_pa else lg_r_per_pa

    if denominator <= 0:
        return None

    # 타석당 기여 득점
    player_r_per_pa = wraa / pa + lg_r_per_pa

    # 파크팩터 보정
    park_adjustment = lg_r_per_pa - (park_factor * lg_r_per_pa)

    wrc_plus = ((player_r_per_pa + park_adjustment) / denominator) * 100

    # 클리핑 (극단값 방지)
    wrc_plus = max(0, min(300, wrc_plus))

    return round(wrc_plus, 1)


# ============================================================
# 리그 상수 계산
# ============================================================

def calculate_league_woba(hitting_df: pd.DataFrame, weights: Optional[dict] = None) -> float:
    """
    리그 평균 wOBA를 계산한다.

    Args:
        hitting_df: 타자 기록 DataFrame
        weights: wOBA 가중치

    Returns:
        리그 평균 wOBA
    """
    w = weights or DEFAULT_WOBA_WEIGHTS

    cols = _resolve_hitting_columns(hitting_df)

    total_bb = hitting_df[cols["BB"]].sum() if cols["BB"] else 0
    total_ibb = hitting_df[cols["IBB"]].sum() if cols["IBB"] else 0
    total_hbp = hitting_df[cols["HBP"]].sum() if cols["HBP"] else 0
    total_h = hitting_df[cols["H"]].sum() if cols["H"] else 0
    total_2b = hitting_df[cols["2B"]].sum() if cols["2B"] else 0
    total_3b = hitting_df[cols["3B"]].sum() if cols["3B"] else 0
    total_hr = hitting_df[cols["HR"]].sum() if cols["HR"] else 0
    total_ab = hitting_df[cols["AB"]].sum() if cols["AB"] else 0
    total_sf = hitting_df[cols["SF"]].sum() if cols["SF"] else 0

    total_1b = total_h - total_2b - total_3b - total_hr

    denominator = total_ab + (total_bb - total_ibb) + total_sf + total_hbp
    if denominator <= 0:
        return 0.0

    numerator = (
        w["BB"] * (total_bb - total_ibb)
        + w["HBP"] * total_hbp
        + w["1B"] * total_1b
        + w["2B"] * total_2b
        + w["3B"] * total_3b
        + w["HR"] * total_hr
    )

    lg_woba = numerator / denominator
    logger.info(f"리그 평균 wOBA: {lg_woba:.4f}")
    return round(lg_woba, 4)


def calculate_league_r_per_pa(hitting_df: pd.DataFrame) -> float:
    """
    리그 평균 타석당 득점(R/PA)을 계산한다.

    Args:
        hitting_df: 타자 기록 DataFrame

    Returns:
        리그 평균 R/PA
    """
    cols = _resolve_hitting_columns(hitting_df)

    r_col = cols.get("R")
    pa_col = cols.get("PA")

    if not r_col or not pa_col:
        logger.error("득점(R) 또는 타석(PA) 컬럼을 찾을 수 없음")
        return 0.0

    total_r = hitting_df[r_col].sum()
    total_pa = hitting_df[pa_col].sum()

    if total_pa <= 0:
        return 0.0

    r_per_pa = total_r / total_pa
    logger.info(f"리그 R/PA: {r_per_pa:.4f} (총 {total_r}득점, 총 {total_pa}타석)")
    return round(r_per_pa, 4)


def calculate_team_wrc_plus(
    hitting_df: pd.DataFrame,
    park_factors: Optional[pd.DataFrame] = None,
    min_pa: int = 0,
    weights: Optional[dict] = None,
) -> pd.DataFrame:
    """
    전체 타자의 wRC+를 일괄 계산한다.

    Args:
        hitting_df: 타자 기록 DataFrame
        park_factors: 팀별 파크팩터 DataFrame (컬럼: 팀, park_factor)
        min_pa: 최소 타석 기준 (0이면 전체 포함)
        weights: wOBA 가중치

    Returns:
        wOBA, wRAA, wRC+ 컬럼이 추가된 DataFrame
    """
    w = weights or DEFAULT_WOBA_WEIGHTS
    df = hitting_df.copy()
    cols = _resolve_hitting_columns(df)

    # 리그 상수 계산 (필터 전 전체 데이터)
    lg_woba = calculate_league_woba(hitting_df, weights)
    lg_r_per_pa = calculate_league_r_per_pa(hitting_df)

    # 최소 타석 필터
    pa_col = cols.get("PA")
    if min_pa > 0 and pa_col:
        df = df[df[pa_col] >= min_pa].copy()

    # 파크팩터 매핑
    team_col = _find_col(df, ["팀", "Team"])
    if park_factors is not None and team_col:
        pf_map = dict(zip(park_factors["팀"], park_factors["park_factor"]))
        df["_pf"] = df[team_col].map(pf_map).fillna(1.0)
    else:
        df["_pf"] = 1.0

    # 개별 타자 wOBA 계산
    def _row_woba(row):
        h = row.get(cols["H"], 0) or 0
        doubles = row.get(cols["2B"], 0) or 0
        triples = row.get(cols["3B"], 0) or 0
        hr = row.get(cols["HR"], 0) or 0
        singles = h - doubles - triples - hr

        return calculate_woba(
            bb=row.get(cols["BB"], 0) or 0,
            hbp=row.get(cols["HBP"], 0) or 0,
            singles=max(0, singles),
            doubles=doubles,
            triples=triples,
            hr=hr,
            ab=row.get(cols["AB"], 0) or 0,
            sf=row.get(cols["SF"], 0) or 0,
            ibb=row.get(cols["IBB"], 0) or 0,
            weights=w,
        )

    df["wOBA"] = df.apply(_row_woba, axis=1)

    # wRAA 계산
    def _row_wraa(row):
        if row["wOBA"] is None or pd.isna(row["wOBA"]):
            return None
        pa = row.get(pa_col, 0) or 0
        return calculate_wraa(row["wOBA"], lg_woba, pa)

    df["wRAA"] = df.apply(_row_wraa, axis=1)

    # wRC+ 계산
    def _row_wrc_plus(row):
        if row["wRAA"] is None or pd.isna(row["wRAA"]):
            return None
        pa = row.get(pa_col, 0) or 0
        return calculate_wrc_plus(
            wraa=row["wRAA"],
            pa=pa,
            lg_r_per_pa=lg_r_per_pa,
            park_factor=row["_pf"],
        )

    df["wRC+"] = df.apply(_row_wrc_plus, axis=1)

    # 메타데이터
    df["lg_wOBA"] = lg_woba
    df["lg_R/PA"] = lg_r_per_pa
    df.drop(columns=["_pf"], inplace=True)

    calculated = df["wRC+"].notna().sum()
    logger.info(f"wRC+ 계산 완료: {calculated}/{len(df)}명")

    return df


# ============================================================
# 유틸리티
# ============================================================

def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """DataFrame에서 후보 컬럼명 중 존재하는 것을 찾는다."""
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _resolve_hitting_columns(df: pd.DataFrame) -> dict:
    """
    타자 기록 DataFrame의 컬럼명을 표준화된 키로 매핑한다.
    KBO 공식 사이트의 한글 컬럼명과 영문 컬럼명 모두 지원.
    """
    mapping = {
        "H": ["안타", "H", "Hits"],
        "2B": ["2타", "2루타", "2B", "Doubles"],
        "3B": ["3타", "3루타", "3B", "Triples"],
        "HR": ["홈런", "HR", "HomeRuns"],
        "BB": ["볼넷", "사사구", "BB", "Walks"],
        "IBB": ["고의사구", "고의4구", "IBB"],
        "HBP": ["사구", "몸에맞는공", "HBP"],
        "AB": ["타수", "AB", "AtBats"],
        "PA": ["타석", "PA", "PlateAppearances"],
        "SF": ["희비", "희생플라이", "SF"],
        "R": ["득점", "R", "Runs"],
    }

    resolved = {}
    for key, candidates in mapping.items():
        resolved[key] = _find_col(df, candidates)

    return resolved


# ============================================================
# DB 기반 전 연도 wRC+ 계산 (era_plus.py / ops_plus.py와 동일 패턴)
# ============================================================

import sqlite3


def calculate_wrc_plus_all(db_path, pf_data, min_pa_ratio=3.1, weights=None):
    """
    전 연도 wRC+ 계산 (DB 직접 읽기)

    Args:
        db_path: kbo_data.db 경로
        pf_data: 파크팩터 데이터 {year: {team: pf_value}}
        min_pa_ratio: 규정타석 = 팀 최대경기수 × 이 값 (MLB 기준 3.1)
        weights: wOBA 가중치 (None이면 Tom Tango 기본값)

    Returns:
        {year: [{"Player_ID", "선수명", "팀명", "wOBA", "wRAA", "wRC+", ...}]}
    """
    w = weights or DEFAULT_WOBA_WEIGHTS
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    results = {}

    for year in range(1982, 2026):
        t1 = f'kbo_hitting_basic1_{year}'
        t2 = f'kbo_hitting_basic2_{year}'

        # 테이블 존재 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t1,))
        if not cursor.fetchone():
            continue
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t2,))
        if not cursor.fetchone():
            continue

        # basic1: Player_ID, 선수명, 팀명, PA, AB, H, 2B, 3B, HR, TB, R, RBI, SF, SAC, G, AVG
        cursor.execute(f"""
            SELECT Player_ID, 선수명, 팀명, PA, AB, H, [2B], [3B], HR, TB, R, RBI, SF, SAC, G, AVG
            FROM [{t1}]
        """)
        basic1 = {row[0]: row for row in cursor.fetchall()}

        # basic2: Player_ID, BB, IBB, HBP, SO, SLG, OBP, OPS
        cursor.execute(f"""
            SELECT Player_ID, BB, IBB, HBP, SO, SLG, OBP, OPS
            FROM [{t2}]
        """)
        basic2 = {row[0]: row for row in cursor.fetchall()}

        if not basic1 or not basic2:
            continue

        # ============ 리그 집계 ============
        lg_bb, lg_ibb, lg_hbp = 0, 0, 0
        lg_h, lg_2b, lg_3b, lg_hr = 0, 0, 0, 0
        lg_ab, lg_sf, lg_r, lg_pa = 0, 0, 0, 0

        for pid, row1 in basic1.items():
            if pid not in basic2:
                continue
            row2 = basic2[pid]
            lg_pa += row1[3] or 0
            lg_ab += row1[4] or 0
            lg_h  += row1[5] or 0
            lg_2b += row1[6] or 0
            lg_3b += row1[7] or 0
            lg_hr += row1[8] or 0
            lg_r  += row1[10] or 0
            lg_sf += row1[12] or 0
            lg_bb  += row2[1] or 0
            lg_ibb += row2[2] or 0
            lg_hbp += row2[3] or 0

        if lg_ab == 0 or lg_pa == 0:
            continue

        lg_1b = lg_h - lg_2b - lg_3b - lg_hr

        # 리그 wOBA
        lg_woba_denom = lg_ab + (lg_bb - lg_ibb) + lg_sf + lg_hbp
        if lg_woba_denom <= 0:
            continue
        lg_woba = (
            w["BB"] * (lg_bb - lg_ibb)
            + w["HBP"] * lg_hbp
            + w["1B"] * lg_1b
            + w["2B"] * lg_2b
            + w["3B"] * lg_3b
            + w["HR"] * lg_hr
        ) / lg_woba_denom

        # wOBA Scale 근사: lgwOBA / lgOBP
        lg_obp_denom = lg_ab + lg_bb + lg_hbp + lg_sf
        lg_obp = (lg_h + lg_bb + lg_hbp) / lg_obp_denom if lg_obp_denom > 0 else 0
        woba_scale = lg_woba / lg_obp if lg_obp > 0 else DEFAULT_WOBA_SCALE

        # 리그 R/PA
        lg_r_per_pa = lg_r / lg_pa

        # ============ 규정타석 ============
        max_g = max((row[14] for row in basic1.values() if row[14]), default=144)
        min_pa = max_g * min_pa_ratio

        # ============ 개인 wRC+ 계산 ============
        year_results = []

        for pid, row1 in basic1.items():
            if pid not in basic2:
                continue
            row2 = basic2[pid]

            pa  = row1[3] or 0
            ab  = row1[4] or 0
            h   = row1[5] or 0
            dbl = row1[6] or 0
            tpl = row1[7] or 0
            hr  = row1[8] or 0
            r   = row1[10] or 0
            rbi = row1[11] or 0
            sf  = row1[12] or 0
            avg = row1[15] or 0

            bb  = row2[1] or 0
            ibb = row2[2] or 0
            hbp = row2[3] or 0
            slg = row2[5] or 0
            obp = row2[6] or 0
            ops = row2[7] or 0

            if pa < min_pa:
                continue

            singles = h - dbl - tpl - hr
            if singles < 0:
                singles = 0

            # 개인 wOBA
            woba_denom = ab + (bb - ibb) + sf + hbp
            if woba_denom <= 0:
                continue
            player_woba = (
                w["BB"] * (bb - ibb)
                + w["HBP"] * hbp
                + w["1B"] * singles
                + w["2B"] * dbl
                + w["3B"] * tpl
                + w["HR"] * hr
            ) / woba_denom

            # wRAA
            wraa = ((player_woba - lg_woba) / woba_scale) * pa

            # 파크팩터
            team = row1[2]
            pf = pf_data.get(year, {}).get(team, 100) / 100

            # wRC+
            player_r_per_pa = wraa / pa + lg_r_per_pa
            park_adj = lg_r_per_pa - (pf * lg_r_per_pa)
            wrc_plus = ((player_r_per_pa + park_adj) / lg_r_per_pa) * 100

            year_results.append({
                'Player_ID': pid,
                '선수명': row1[1],
                '팀명': team,
                'AVG': avg,
                'OBP': obp,
                'SLG': slg,
                'OPS': ops,
                'PA': pa,
                'HR': hr,
                'RBI': rbi,
                'wOBA': round(player_woba, 4),
                'wRAA': round(wraa, 2),
                'lgwOBA': round(lg_woba, 4),
                'lgR/PA': round(lg_r_per_pa, 4),
                'PF': round(pf * 100, 1),
                'wRC+': round(wrc_plus, 1),
            })

        # wRC+ 내림차순 정렬
        year_results.sort(key=lambda x: x['wRC+'], reverse=True)
        results[year] = year_results

    conn.close()
    return results


# ============================================================
# 단독 실행 테스트
# ============================================================
if __name__ == "__main__":
    import sys
    sys.path.insert(0, '.')
    from era_plus import load_park_factors

    pf_files = [
        'kbo_statiz_data_1982_1998_.xlsx',
        'kbo_statiz_data_1999_2009_.xlsx',
        'kbo_statiz_data_2010_2021_.xlsx',
        'kbo_statiz_data_2022_2024_.xlsx',
    ]
    pf_data = load_park_factors(pf_files)
    results = calculate_wrc_plus_all('kbo_data.db', pf_data)

    for year in [1982, 1995, 2010, 2025]:
        if year in results and results[year]:
            top = results[year][0]
            cnt = len(results[year])
            print(f"{year}: {cnt}명 | 1위 {top['선수명']}({top['팀명']}) wRC+ {top['wRC+']} wOBA {top['wOBA']}")

