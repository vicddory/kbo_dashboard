"""
FA 적정가 모델 — Phase 1
성적 기반 가치 산출 + 과거 계약 비교

입력: 선수 이름 (또는 Player_ID) + FA 연도
출력: 가중 WAR, 성적 등급, 적정가 범위, 유사 계약 비교

사용법:
    from fa_value_model import FAValueModel
    model = FAValueModel('kbo_data.db', pf_data, 'fa_contracts.json')
    result = model.estimate('강백호', fa_year=2026)
"""

import sqlite3
import json
import re
import os
import statistics
from typing import Optional
from proxy_war import calculate_proxy_war_all, parse_ip, get_kbo_games
from wrc_plus import calculate_wrc_plus_all
from era_plus import load_park_factors, calculate_era_plus


class FAValueModel:

    # 성적 가중치
    WEIGHT_FA_SEASON = 0.70
    WEIGHT_PREV_SEASON = 0.20
    WEIGHT_CAREER_AVG = 0.10

    def __init__(self, db_path, pf_data, fa_json_path):
        """
        Args:
            db_path: kbo_data.db 경로
            pf_data: 파크팩터 데이터 {year: {team: pf}}
            fa_json_path: fa_contracts.json 경로
        """
        self.db_path = db_path
        self.pf_data = pf_data

        # Proxy WAR 전 연도 계산
        print("[FAModel] Proxy WAR 계산 중...")
        self.war_data = calculate_proxy_war_all(db_path, pf_data)

        # wRC+ 전 연도 계산
        print("[FAModel] wRC+ 계산 중...")
        self.wrc_data = calculate_wrc_plus_all(db_path, pf_data)

        # ERA+ 전 연도 계산
        print("[FAModel] ERA+ 계산 중...")
        self.era_data = calculate_era_plus(db_path, pf_data)

        # FA 계약 데이터
        resolved_fa_json_path = fa_json_path
        if not os.path.exists(resolved_fa_json_path):
            alt_path = os.path.join(os.path.dirname(__file__), "fa_contracts.json")
            if os.path.exists(alt_path):
                resolved_fa_json_path = alt_path
        with open(resolved_fa_json_path, "r", encoding="utf-8") as f:
            self.fa_contracts = json.load(f)["contracts"]

        # Player_ID → 이름 매핑 (DB에서)
        self._build_player_index()

        # WAR당 가격 계수 계산
        self._calc_market_coefficients()

        print("[FAModel] 초기화 완료")

    def _build_player_index(self):
        """DB에서 선수 이름 → Player_ID 인덱스 구축"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        self.name_to_ids = {}  # {name: [(pid, team, year), ...]}
        self.id_to_name = {}

        for year in range(1982, 2026):
            for tbl in [f"kbo_hitting_basic1_{year}", f"kbo_pitching_basic1_{year}"]:
                try:
                    cursor.execute(f"SELECT Player_ID, 선수명, 팀명 FROM [{tbl}]")
                    for pid, name, team in cursor.fetchall():
                        if name not in self.name_to_ids:
                            self.name_to_ids[name] = []
                        self.name_to_ids[name].append((pid, team, year))
                        self.id_to_name[pid] = name
                except:
                    pass
        conn.close()

    def _calc_market_coefficients(self):
        """과거 FA 계약 데이터에서 WAR당 가격 계수를 도출"""
        data_points = []

        for c in self.fa_contracts:
            name = c["name"]
            fa_year = c["year"]
            perf_year = fa_year - 1  # FA 직전 시즌 = 성적 기준 시즌
            total = c["total"]
            duration_years = self._parse_duration(c["duration"])

            if duration_years <= 0 or total <= 0:
                continue

            annual = total / duration_years

            # 해당 선수의 perf_year WAR 찾기
            war = self._find_player_war(name, perf_year, c.get("team", c.get("from", "")))
            if war is None:
                continue

            if war > 0:
                price_per_war = annual / war
                data_points.append({
                    "name": name, "year": fa_year,
                    "war": war, "annual": annual,
                    "price_per_war": price_per_war,
                    "total": total, "duration": duration_years,
                    "pos": c["pos"], "type": c["type"],
                })

        self.market_data = data_points

        if data_points:
            # 최근 5년 데이터에 가중치
            recent = [d for d in data_points if d["year"] >= 2022]
            older = [d for d in data_points if d["year"] < 2022]

            if recent:
                self.war_price_recent = sum(d["price_per_war"] for d in recent) / len(recent)
            else:
                self.war_price_recent = 0

            all_prices = [d["price_per_war"] for d in data_points]
            self.war_price_avg = sum(all_prices) / len(all_prices)
            self.war_price_median = statistics.median(all_prices)
        else:
            self.war_price_recent = 5.0  # 기본값: WAR 1당 5억
            self.war_price_avg = 5.0
            self.war_price_median = 5.0

    def _parse_duration(self, duration_str):
        """'4년' → 4, '3+1년' → 4, '2+2년' → 4, '4+2년' → 6"""
        nums = re.findall(r"(\d+)", duration_str)
        if nums:
            return sum(int(n) for n in nums)
        return 0

    def _find_player_war(self, name, year, team_hint=""):
        """선수 이름 + 연도로 WAR 찾기"""
        # 타자에서 찾기
        batters = self.war_data["batter"].get(year, [])
        for b in batters:
            if b["선수명"] == name:
                if team_hint and b["팀명"] != team_hint:
                    continue
                return b["ProxyWAR"]

        # 팀 힌트 무시하고 다시 찾기
        for b in batters:
            if b["선수명"] == name:
                return b["ProxyWAR"]

        # 투수에서 찾기
        pitchers = self.war_data["pitcher"].get(year, [])
        for p in pitchers:
            if p["선수명"] == name:
                if team_hint and p["팀명"] != team_hint:
                    continue
                return p["ProxyWAR"]

        for p in pitchers:
            if p["선수명"] == name:
                return p["ProxyWAR"]

        return None

    def _find_player_wrc(self, name, year, team_hint=""):
        """선수 이름 + 연도로 wRC+ 찾기"""
        data = self.wrc_data.get(year, [])
        for d in data:
            if d["선수명"] == name:
                if team_hint and d["팀명"] != team_hint:
                    continue
                return d["wRC+"]
        for d in data:
            if d["선수명"] == name:
                return d["wRC+"]
        return None

    def _find_player_era_plus(self, name, year, team_hint=""):
        """선수 이름 + 연도로 ERA+ 찾기"""
        data = self.era_data.get(year, [])
        for d in data:
            if d["선수명"] == name:
                if team_hint and d["팀명"] != team_hint:
                    continue
                return d["ERA+"]
        for d in data:
            if d["선수명"] == name:
                return d["ERA+"]
        return None

    def _get_career_wars(self, name, up_to_year, team_hint=""):
        """선수의 커리어 WAR 목록 (up_to_year까지)"""
        wars = []
        for year in range(1982, up_to_year + 1):
            w = self._find_player_war(name, year, team_hint)
            if w is not None:
                wars.append({"year": year, "war": w})
        return wars

    def estimate(self, name, fa_year=2026, team_hint=""):
        """
        FA 적정가 추정

        Args:
            name: 선수 이름
            fa_year: FA 연도 (스토브리그 연도)
            team_hint: 소속팀 힌트 (동명이인 구분용)

        Returns:
            dict with keys: player, weighted_war, grade, estimated_value, comparables, career
        """
        perf_year = fa_year - 1  # 성적 기준 시즌

        # 커리어 WAR
        career = self._get_career_wars(name, perf_year, team_hint)
        if not career:
            return {"error": f"'{name}'의 성적을 찾을 수 없습니다."}

        # 가중 WAR 계산
        fa_season_war = None
        prev_season_war = None
        career_5yr_wars = []

        for c in career:
            if c["year"] == perf_year:
                fa_season_war = c["war"]
            elif c["year"] == perf_year - 1:
                prev_season_war = c["war"]
            if c["year"] >= perf_year - 5 and c["year"] < perf_year:
                career_5yr_wars.append(c["war"])

        # 가중 합산
        weighted = 0
        components = {}

        if fa_season_war is not None:
            weighted += fa_season_war * self.WEIGHT_FA_SEASON
            components["fa_season"] = {"year": perf_year, "war": fa_season_war, "weight": 0.70}

        if prev_season_war is not None:
            weighted += prev_season_war * self.WEIGHT_PREV_SEASON
            components["prev_season"] = {"year": perf_year - 1, "war": prev_season_war, "weight": 0.20}
        elif fa_season_war is not None:
            # 직전 시즌이 없으면 FA 시즌으로 대체
            weighted += fa_season_war * self.WEIGHT_PREV_SEASON
            components["prev_season"] = {"year": perf_year, "war": fa_season_war, "weight": 0.20, "note": "직전 시즌 없음, FA 시즌으로 대체"}

        if career_5yr_wars:
            avg_5yr = sum(career_5yr_wars) / len(career_5yr_wars)
            weighted += avg_5yr * self.WEIGHT_CAREER_AVG
            components["career_avg"] = {"years": f"{perf_year-5}~{perf_year-1}", "war": round(avg_5yr, 2), "weight": 0.10}
        elif fa_season_war is not None:
            weighted += fa_season_war * self.WEIGHT_CAREER_AVG
            components["career_avg"] = {"war": fa_season_war, "weight": 0.10, "note": "과거 데이터 없음, FA 시즌으로 대체"}

        # 포지션 판단 (타자/투수)
        is_pitcher = self._find_player_war(name, perf_year, team_hint) is None or \
                     any(p["선수명"] == name for p in self.war_data["pitcher"].get(perf_year, []))
        is_batter = any(b["선수명"] == name for b in self.war_data["batter"].get(perf_year, []))

        # 보조 지표
        supplementary = {}
        if is_batter:
            wrc = self._find_player_wrc(name, perf_year, team_hint)
            if wrc is not None:
                supplementary["wRC+"] = wrc
        if is_pitcher:
            era_plus = self._find_player_era_plus(name, perf_year, team_hint)
            if era_plus is not None:
                supplementary["ERA+"] = era_plus

        # 등급
        grade = self._grade_war(weighted)

        # 적정가 추정
        price_low = weighted * self.war_price_median * 0.8
        price_mid = weighted * self.war_price_recent
        price_high = weighted * self.war_price_recent * 1.3

        # 유사 계약 찾기
        comparables = self._find_comparables(weighted, is_pitcher and not is_batter)

        # 팀 정보
        team = ""
        for c in reversed(career):
            w = self._find_player_war(name, c["year"], team_hint)
            if w is not None:
                # 해당 연도의 팀 찾기
                batters = self.war_data["batter"].get(c["year"], [])
                for b in batters:
                    if b["선수명"] == name:
                        team = b["팀명"]
                        break
                if not team:
                    pitchers = self.war_data["pitcher"].get(c["year"], [])
                    for p in pitchers:
                        if p["선수명"] == name:
                            team = p["팀명"]
                            break
                if team:
                    break

        return {
            "player": name,
            "team": team,
            "fa_year": fa_year,
            "perf_year": perf_year,
            "weighted_war": round(weighted, 2),
            "components": components,
            "grade": grade,
            "supplementary": supplementary,
            "career_wars": career,
            "estimated_value": {
                "annual_low": round(max(0, price_low), 1),
                "annual_mid": round(max(0, price_mid), 1),
                "annual_high": round(max(0, price_high), 1),
                "war_price_basis": round(self.war_price_recent, 2),
                "unit": "억원/년",
            },
            "comparables": comparables[:5],
            "market_stats": {
                "war_price_recent_avg": round(self.war_price_recent, 2),
                "war_price_all_avg": round(self.war_price_avg, 2),
                "war_price_median": round(self.war_price_median, 2),
                "sample_size": len(self.market_data),
            },
        }

    def _grade_war(self, war):
        """WAR 기반 등급 판정"""
        if war >= 6:
            return {"label": "MVP급", "tier": "S"}
        elif war >= 4:
            return {"label": "올스타급", "tier": "A"}
        elif war >= 2:
            return {"label": "주전급", "tier": "B"}
        elif war >= 1:
            return {"label": "백업급", "tier": "C"}
        else:
            return {"label": "대체선수 수준", "tier": "D"}

    def _find_comparables(self, target_war, is_pitcher=False):
        """가중 WAR이 비슷한 과거 FA 계약 찾기"""
        comps = []
        for d in self.market_data:
            if is_pitcher and d["pos"] != "투수":
                continue
            if not is_pitcher and d["pos"] != "야수":
                continue
            diff = abs(d["war"] - target_war)
            comps.append({**d, "_diff": diff})

        comps.sort(key=lambda x: x["_diff"])
        return [
            {
                "name": c["name"], "year": c["year"], "war": round(c["war"], 2),
                "total": c["total"], "duration": c["duration"],
                "annual": round(c["annual"], 1), "type": c["type"],
            }
            for c in comps[:5]
        ]


# ============================================================
# 단독 실행 테스트
# ============================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")

    pf_files = [
        "kbo_statiz_data_1982_1998_.xlsx",
        "kbo_statiz_data_1999_2009_.xlsx",
        "kbo_statiz_data_2010_2021_.xlsx",
        "kbo_statiz_data_2022_2024_.xlsx",
    ]
    pf_data = load_park_factors(pf_files)

    model = FAValueModel("kbo_data.db", pf_data, "fa_contracts.json")

    # 테스트: 2026 FA
    test_players = ["강백호", "박해민", "양현종"]
    for name in test_players:
        print(f"\n{'='*50}")
        result = model.estimate(name, fa_year=2026)
        if "error" in result:
            print(f"{name}: {result['error']}")
            continue

        print(f"선수: {result['player']} ({result['team']})")
        print(f"FA 연도: {result['fa_year']} (성적 기준: {result['perf_year']})")
        print(f"가중 WAR: {result['weighted_war']}")
        print(f"등급: {result['grade']['label']} ({result['grade']['tier']})")

        if result["supplementary"]:
            print(f"보조 지표: {result['supplementary']}")

        ev = result["estimated_value"]
        print(f"적정 연봉: {ev['annual_low']}~{ev['annual_high']}억/년 (중앙: {ev['annual_mid']}억)")

        if result["comparables"]:
            print(f"유사 계약:")
            for c in result["comparables"][:3]:
                print(f"  {c['year']} {c['name']} WAR {c['war']} → {c['total']}억/{c['duration']}년 (연 {c['annual']}억)")
