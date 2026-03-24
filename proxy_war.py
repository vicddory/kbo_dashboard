"""
Proxy WAR 계산 모듈 (KBO 세이버메트릭스 대시보드)

타자: Batting Runs + wSB + Positional Adj + League Adj + Replacement Runs → WAR
투수: RA9 기반 bWAR 방식 (FIP 대신 RA9 — 영상추적 불필요)

라벨: "Proxy WAR (수비 제외)" — UZR/UBR 미포함

필요 DB 테이블:
    - kbo_hitting_basic1_{연도} (1982~2025)
    - kbo_hitting_basic2_{연도} (1982~2025)
    - kbo_pitching_basic1_{연도} (1982~2025)
    - kbo_fielding_basic_{연도} (2001~2025) — 포지션, 수비이닝
    - kbo_runner_basic_{연도} (2001~2025) — SB, CS

참조: kbo_proxy_war_spec.md
"""

import sqlite3
import re
from typing import Optional

# wOBA 가중치 (Tom Tango 기본값 — 추후 연도별 재계산으로 교체 가능)
DEFAULT_WOBA_WEIGHTS = {
    "BB": 0.69, "HBP": 0.72, "1B": 0.89,
    "2B": 1.27, "3B": 1.62, "HR": 2.10,
}

# 포지션 보정값 (런 / 162게임 기준, FanGraphs 표준)
# KBO 144경기로 스케일링: × 144/162 = 0.8889
POSITION_ADJ_162 = {
    "포수": 12.5, "1루수": -12.5, "2루수": 2.5,
    "3루수": 2.5, "유격수": 7.5, "좌익수": -7.5,
    "중견수": 2.5, "우익수": -7.5, "지명타자": -17.5,
    "투수": 0,  # 투수 수비는 WAR에서 별도 처리
}

KBO_GAMES = 144  # KBO 정규시즌 경기수 (기본값, 실제는 연도별 다름)
SCALE_FACTOR = KBO_GAMES / 162  # 0.8889

# KBO 연도별 정규시즌 경기수
KBO_GAMES_BY_YEAR = {
    1982: 80,
    **{y: 100 for y in range(1983, 1985)},
    1985: 110,
    **{y: 108 for y in range(1986, 1989)},
    **{y: 120 for y in range(1989, 1991)},
    **{y: 126 for y in range(1991, 1999)},
    1999: 132,
    **{y: 133 for y in range(2000, 2005)},
    **{y: 126 for y in range(2005, 2009)},
    **{y: 133 for y in range(2009, 2013)},
    **{y: 128 for y in range(2013, 2015)},
    **{y: 144 for y in range(2015, 2030)},
}


def get_kbo_games(year):
    """해당 연도의 KBO 정규시즌 경기수 반환"""
    return KBO_GAMES_BY_YEAR.get(year, 144)


def parse_ip(ip_str):
    """'740 1/3' → 740.333, '19' → 19.0"""
    if isinstance(ip_str, (int, float)):
        return float(ip_str)
    if not ip_str or ip_str == '':
        return 0.0
    ip_str = str(ip_str).strip()
    m = re.match(r"(\d+)\s+(\d)/(\d)", ip_str)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    try:
        return float(ip_str)
    except:
        return 0.0


# ============================================================
# 리그 집계 계산
# ============================================================

def calc_league_stats(cursor, year, weights=None):
    """연도별 리그 집계 계산 — wOBA, R/PA, RPW 등"""
    w = weights or DEFAULT_WOBA_WEIGHTS

    t1 = f"kbo_hitting_basic1_{year}"
    t2 = f"kbo_hitting_basic2_{year}"
    tp = f"kbo_pitching_basic1_{year}"

    # 타자 합산
    cursor.execute(f"""
        SELECT b1.Player_ID, b1.PA, b1.AB, b1.H, b1.[2B], b1.[3B], b1.HR,
               b1.R, b1.SF, b1.G,
               b2.BB, b2.IBB, b2.HBP
        FROM [{t1}] b1
        JOIN [{t2}] b2 ON b1.Player_ID = b2.Player_ID
    """)
    rows = cursor.fetchall()

    if not rows:
        return None

    lg = {
        "PA": 0, "AB": 0, "H": 0, "2B": 0, "3B": 0, "HR": 0,
        "R": 0, "SF": 0, "BB": 0, "IBB": 0, "HBP": 0,
    }
    max_g = 0

    for row in rows:
        lg["PA"]  += row[1] or 0
        lg["AB"]  += row[2] or 0
        lg["H"]   += row[3] or 0
        lg["2B"]  += row[4] or 0
        lg["3B"]  += row[5] or 0
        lg["HR"]  += row[6] or 0
        lg["R"]   += row[7] or 0
        lg["SF"]  += row[8] or 0
        lg["BB"]  += row[10] or 0
        lg["IBB"] += row[11] or 0
        lg["HBP"] += row[12] or 0
        g = row[9] or 0
        if g > max_g:
            max_g = g

    lg["1B"] = lg["H"] - lg["2B"] - lg["3B"] - lg["HR"]
    lg["max_G"] = get_kbo_games(year)  # 연도별 정규시즌 경기수 사용

    if lg["AB"] == 0 or lg["PA"] == 0:
        return None

    # 리그 wOBA
    woba_denom = lg["AB"] + (lg["BB"] - lg["IBB"]) + lg["SF"] + lg["HBP"]
    if woba_denom <= 0:
        return None
    lg["wOBA"] = (
        w["BB"] * (lg["BB"] - lg["IBB"])
        + w["HBP"] * lg["HBP"]
        + w["1B"] * lg["1B"]
        + w["2B"] * lg["2B"]
        + w["3B"] * lg["3B"]
        + w["HR"] * lg["HR"]
    ) / woba_denom

    # wOBA Scale
    lg_obp_denom = lg["AB"] + lg["BB"] + lg["HBP"] + lg["SF"]
    lg["OBP"] = (lg["H"] + lg["BB"] + lg["HBP"]) / lg_obp_denom if lg_obp_denom > 0 else 0
    lg["wOBA_Scale"] = lg["wOBA"] / lg["OBP"] if lg["OBP"] > 0 else 1.15

    # R/PA
    lg["R/PA"] = lg["R"] / lg["PA"]

    # RPW = 9 × (lgR / lgIP) × 1.5 + 3
    try:
        cursor.execute(f"SELECT IP FROM [{tp}]")
        total_ip = sum(parse_ip(r[0]) for r in cursor.fetchall())
        cursor.execute(f"SELECT SUM(R) FROM [{tp}]")
        total_r_pitch = cursor.fetchone()[0] or 0
    except:
        total_ip = lg["PA"] * 0.37  # 근사
        total_r_pitch = lg["R"]

    if total_ip > 0:
        lg["RA9"] = (total_r_pitch * 9) / total_ip
        lg["RPW"] = 9 * (total_r_pitch / total_ip) * 1.5 + 3
    else:
        lg["RA9"] = 4.5
        lg["RPW"] = 10

    lg["IP"] = total_ip
    lg["R_pitch"] = total_r_pitch

    # 리그 wSB 평균 (주루 데이터 있을 때)
    lg["wSB_per_opp"] = 0  # 기본값, runner 테이블 있으면 계산

    # RunsPerOut
    total_outs = total_ip * 3 if total_ip > 0 else 1
    lg["RunsPerOut"] = total_r_pitch / total_outs

    return lg


# ============================================================
# 타자 Proxy WAR
# ============================================================

def calc_batter_proxy_war(cursor, year, pf_data, lg, weights=None):
    """
    특정 연도 타자 Proxy WAR 일괄 계산

    Returns:
        [{Player_ID, 선수명, 팀명, wOBA, wRAA, BattingRuns, wSB,
          PosAdj, LeagueAdj, ReplacementRuns, ProxyWAR, ...}]
    """
    w = weights or DEFAULT_WOBA_WEIGHTS

    t1 = f"kbo_hitting_basic1_{year}"
    t2 = f"kbo_hitting_basic2_{year}"

    cursor.execute(f"""
        SELECT b1.Player_ID, b1.선수명, b1.팀명,
               b1.PA, b1.AB, b1.H, b1.[2B], b1.[3B], b1.HR,
               b1.R, b1.RBI, b1.SF, b1.G, b1.AVG, b1.TB,
               b2.BB, b2.IBB, b2.HBP, b2.OBP, b2.SLG, b2.OPS
        FROM [{t1}] b1
        JOIN [{t2}] b2 ON b1.Player_ID = b2.Player_ID
    """)
    batters = cursor.fetchall()

    # 수비 데이터 (2001~)
    fielding = {}
    ft = f"kbo_fielding_basic_{year}"
    try:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (ft,))
        if cursor.fetchone():
            cursor.execute(f"SELECT Player_ID, POS, IP FROM [{ft}]")
            for pid, pos, ip_str in cursor.fetchall():
                ip = parse_ip(ip_str)
                if pid not in fielding:
                    fielding[pid] = []
                fielding[pid].append((pos, ip))
    except:
        pass

    # 주루 데이터 (2001~)
    runners = {}
    rt = f"kbo_runner_basic_{year}"
    try:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (rt,))
        if cursor.fetchone():
            cursor.execute(f"SELECT Player_ID, SB, CS FROM [{rt}]")
            for pid, sb, cs in cursor.fetchall():
                runners[pid] = (sb or 0, cs or 0)
    except:
        pass

    # 최소 타석 (1타석 이상이면 포함 — 규정타석 제한 없음)
    min_pa = 1

    # 1차: 전체 Batting Runs 합산 (League Adj용)
    all_batting_runs = 0
    all_pa = 0
    player_data = []

    for row in batters:
        pid, name, team = row[0], row[1], row[2]
        pa, ab = row[3] or 0, row[4] or 0
        h, dbl, tpl, hr = row[5] or 0, row[6] or 0, row[7] or 0, row[8] or 0
        r, rbi, sf = row[9] or 0, row[10] or 0, row[11] or 0
        avg = row[13] or 0
        bb, ibb, hbp = row[15] or 0, row[16] or 0, row[17] or 0
        obp, slg, ops = row[18] or 0, row[19] or 0, row[20] or 0

        if pa < min_pa:
            continue

        singles = max(0, h - dbl - tpl - hr)

        # wOBA
        woba_denom = ab + (bb - ibb) + sf + hbp
        if woba_denom <= 0:
            continue
        player_woba = (
            w["BB"] * (bb - ibb) + w["HBP"] * hbp
            + w["1B"] * singles + w["2B"] * dbl
            + w["3B"] * tpl + w["HR"] * hr
        ) / woba_denom

        # wRAA
        wraa = ((player_woba - lg["wOBA"]) / lg["wOBA_Scale"]) * pa

        # Batting Runs (파크팩터 보정)
        pf = pf_data.get(year, {}).get(team, 100) / 100
        batting_runs = wraa + (lg["R/PA"] - pf * lg["R/PA"]) * pa

        # wSB
        sb, cs = runners.get(pid, (0, 0))
        run_cs = -(2 * lg["RunsPerOut"] + 0.075)
        wsb = sb * 0.2 + cs * run_cs
        # 리그 평균 wSB 보정 (간소화: 리그 평균은 ~0이므로 생략)

        # Positional Adjustment
        pos_adj = 0
        kbo_games = lg["max_G"]
        scale = kbo_games / 162
        if pid in fielding:
            for pos, def_ip in fielding[pid]:
                adj_val = POSITION_ADJ_162.get(pos, 0)
                games_equiv = (def_ip / 9) / kbo_games
                pos_adj += adj_val * games_equiv * scale
        else:
            # 수비 데이터 없으면 DH 가정
            pos_adj = POSITION_ADJ_162["지명타자"] * (pa / (kbo_games * 4.5)) * scale

        all_batting_runs += batting_runs
        all_pa += pa

        player_data.append({
            "Player_ID": pid, "선수명": name, "팀명": team,
            "PA": pa, "AVG": avg, "OBP": obp, "SLG": slg, "OPS": ops,
            "HR": hr, "RBI": rbi,
            "wOBA": round(player_woba, 4),
            "wRAA": round(wraa, 2),
            "BattingRuns": round(batting_runs, 2),
            "wSB": round(wsb, 2),
            "PosAdj": round(pos_adj, 2),
            "PF": round(pf * 100, 1),
            "_batting_runs_raw": batting_runs,
            "_pa": pa,
        })

    if not player_data:
        return []

    # League Adjustment: 제로섬 보정
    lg_adj_per_pa = -(all_batting_runs / all_pa) if all_pa > 0 else 0

    results = []
    for p in player_data:
        league_adj = lg_adj_per_pa * p["_pa"]

        # Replacement Runs (근사)
        replacement_runs = 0.1267 * p["_pa"]

        total_runs = (
            p["_batting_runs_raw"]
            + p["wSB"]
            + p["PosAdj"]
            + league_adj
            + replacement_runs
        )

        proxy_war = total_runs / lg["RPW"]

        p["LeagueAdj"] = round(league_adj, 2)
        p["ReplacementRuns"] = round(replacement_runs, 2)
        p["ProxyWAR"] = round(proxy_war, 2)

        # 내부 필드 제거
        del p["_batting_runs_raw"]
        del p["_pa"]
        results.append(p)

    results.sort(key=lambda x: x["ProxyWAR"], reverse=True)
    return results


# ============================================================
# 투수 Proxy WAR (RA9 기반 bWAR)
# ============================================================

def calc_pitcher_proxy_war(cursor, year, pf_data, lg):
    """
    특정 연도 투수 Proxy WAR 일괄 계산

    Returns:
        [{Player_ID, 선수명, 팀명, IP, ERA, RA9, Role, ProxyWAR, ...}]
    """
    tp = f"kbo_pitching_basic1_{year}"

    cursor.execute(f"""
        SELECT Player_ID, 선수명, 팀명, ERA, G, W, L, SV, HLD, IP, H, HR, BB, HBP, SO, R, ER, WHIP
        FROM [{tp}]
    """)
    pitchers = cursor.fetchall()

    # 규정이닝 (선발) / 최소 등판 (불펜)
    min_ip_starter = lg["max_G"] * 1.0  # 규정이닝 (역할 판정용)

    results = []

    for row in pitchers:
        pid, name, team = row[0], row[1], row[2]
        era = row[3] or 0
        g, w, l = row[4] or 0, row[5] or 0, row[6] or 0
        sv, hld = row[7] or 0, row[8] or 0
        ip = parse_ip(row[9])
        h_allowed, hr_allowed = row[10] or 0, row[11] or 0
        bb, hbp, so = row[12] or 0, row[13] or 0, row[14] or 0
        r, er = row[15] or 0, row[16] or 0
        whip = row[17] or 0

        if ip <= 0:
            continue

        # 역할 구분 (최소이닝 제한 없이 전원 포함)
        # 1) 규정이닝 이상 + 승수 > 세이브 → 선발
        # 2) 그 외 SV/HLD 있으면 불펜
        # 3) SV/HLD 없고 등판당 이닝 높으면 선발
        # 4) 나머지 → 불펜
        if ip >= min_ip_starter and w > sv:
            role = "선발"
        elif sv > 0 or hld > 0:
            role = "불펜"
        elif g > 0 and ip / g >= 4.5:
            role = "선발"
        else:
            role = "불펜"

        # RA9
        ra9 = (r * 9) / ip

        # 파크팩터 보정
        pf = pf_data.get(year, {}).get(team, 100) / 100
        ra9_adj = ra9 / pf

        # Replacement RA9
        rep_ra9 = lg["RA9"] * 1.35

        # Runs Above Replacement
        runs_above_rep = (rep_ra9 - ra9_adj) * ip / 9

        # WAR
        proxy_war = runs_above_rep / lg["RPW"]

        results.append({
            "Player_ID": pid,
            "선수명": name,
            "팀명": team,
            "Role": role,
            "IP": ip,
            "ERA": era,
            "RA9": round(ra9, 2),
            "W": w, "L": l, "SV": sv, "HLD": hld,
            "SO": so, "WHIP": whip,
            "PF": round(pf * 100, 1),
            "ProxyWAR": round(proxy_war, 2),
        })

    results.sort(key=lambda x: x["ProxyWAR"], reverse=True)
    return results


# ============================================================
# 전 연도 일괄 계산
# ============================================================

def calculate_proxy_war_all(db_path, pf_data, weights=None):
    """
    전 연도 Proxy WAR 계산

    Args:
        db_path: kbo_data.db 경로
        pf_data: 파크팩터 데이터 {year: {team: pf_value}}
        weights: wOBA 가중치

    Returns:
        {
            "batter": {year: [{선수명, ProxyWAR, ...}]},
            "pitcher": {year: [{선수명, ProxyWAR, ...}]},
        }
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    batter_results = {}
    pitcher_results = {}

    for year in range(1982, 2026):
        t1 = f"kbo_hitting_basic1_{year}"
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t1,))
        if not cursor.fetchone():
            continue

        # 리그 집계
        lg = calc_league_stats(cursor, year, weights)
        if not lg:
            continue

        # 타자
        batters = calc_batter_proxy_war(cursor, year, pf_data, lg, weights)
        if batters:
            batter_results[year] = batters

        # 투수
        pitchers = calc_pitcher_proxy_war(cursor, year, pf_data, lg)
        if pitchers:
            pitcher_results[year] = pitchers

    conn.close()
    return {"batter": batter_results, "pitcher": pitcher_results}


# ============================================================
# 단독 실행 테스트
# ============================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from era_plus import load_park_factors

    pf_files = [
        "kbo_statiz_data_1982_1998_.xlsx",
        "kbo_statiz_data_1999_2009_.xlsx",
        "kbo_statiz_data_2010_2021_.xlsx",
        "kbo_statiz_data_2022_2024_.xlsx",
    ]
    pf_data = load_park_factors(pf_files)
    results = calculate_proxy_war_all("kbo_data.db", pf_data)

    print("=== 타자 Proxy WAR ===")
    for year in [1982, 2000, 2015, 2025]:
        if year in results["batter"]:
            top = results["batter"][year][0]
            cnt = len(results["batter"][year])
            print(f"{year}: {cnt}명 | 1위 {top['선수명']}({top['팀명']}) WAR {top['ProxyWAR']} wOBA {top['wOBA']}")

    print("\n=== 투수 Proxy WAR ===")
    for year in [1982, 2000, 2015, 2025]:
        if year in results["pitcher"]:
            top = results["pitcher"][year][0]
            cnt = len(results["pitcher"][year])
            print(f"{year}: {cnt}명 | 1위 {top['선수명']}({top['팀명']}) WAR {top['ProxyWAR']} RA9 {top['RA9']} ({top['Role']})")
