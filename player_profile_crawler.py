"""
KBO 선수 프로필 크롤러
- 포지션, 생년월일, 연봉, 등번호, 투타, 입단년도 등 수집
- DB의 Player_ID를 기반으로 KBO 공홈 프로필 페이지 크롤링

사용법:
    python player_profile_crawler.py

출력:
    player_profiles.json — 전체 선수 프로필
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import time
import os
import re
from datetime import datetime, date

# ============================================================
# 설정
# ============================================================
DB_PATH = r"C:\Users\user\Downloads\kbo_dashboard/kbo_data.db"
OUTPUT_PATH = "player_profiles.json"
BASE_URL = "https://www.koreabaseball.com/Record/Player"

HITTER_URL = f"{BASE_URL}/HitterDetail/Basic.aspx?playerId="
PITCHER_URL = f"{BASE_URL}/PitcherDetail/Basic.aspx?playerId="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

REQUEST_DELAY = 1.0  # 초


# ============================================================
# 프로필 파싱
# ============================================================
def parse_profile(html):
    """프로필 페이지 HTML에서 선수 정보 추출"""
    soup = BeautifulSoup(html, "html.parser")

    profile = {}

    # 프로필 테이블에서 key:value 추출
    # 형식: "선수명: 고영표", "생년월일: 1991년 09월 16일" 등
    player_info = soup.find("div", class_="player_info")
    if not player_info:
        # 대체 셀렉터 시도
        player_info = soup.find("div", {"id": "contents_area"})

    if not player_info:
        return None

    text = player_info.get_text(separator="\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for line in lines:
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()

            if "선수명" in key:
                profile["name"] = val
            elif "생년월일" in key:
                profile["birth_date_raw"] = val
                profile["birth_date"] = parse_birth_date(val)
            elif "포지션" in key:
                profile["position_raw"] = val
                pos, throw_bat = parse_position(val)
                profile["position"] = pos
                profile["throw_bat"] = throw_bat
            elif "등번호" in key:
                profile["number"] = val.replace("No.", "").strip()
            elif "신장" in key or "체중" in key:
                profile["physical"] = val
            elif "연봉" in key:
                profile["salary_raw"] = val
                profile["salary"] = parse_salary(val)
            elif "입단" in key and "계약금" not in key:
                profile["debut_raw"] = val
                profile["debut_year"] = parse_debut_year(val)
            elif "입단 계약금" in key:
                profile["signing_bonus_raw"] = val
            elif "경력" in key:
                profile["career_path"] = val
            elif "지명순위" in key:
                profile["draft"] = val

    return profile if profile else None


def parse_birth_date(raw):
    """'1991년 09월 16일' → '1991-09-16'"""
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def parse_position(raw):
    """'투수(우언우타)' → ('투수', '우투우타') / '내야수(우투우타)' → ('내야수', '우투우타')"""
    pos = raw
    throw_bat = None

    m = re.match(r"([^(]+)\(([^)]+)\)", raw)
    if m:
        pos = m.group(1).strip()
        throw_bat = m.group(2).strip()

    return pos, throw_bat


def parse_salary(raw):
    """'260000만원' → 2600000000 (원)"""
    m = re.search(r"([\d,]+)\s*만", raw)
    if m:
        num = int(m.group(1).replace(",", ""))
        return num * 10000
    return None


def parse_debut_year(raw):
    """'14KT' → 2014, '02삼성' → 2002"""
    m = re.match(r"(\d{2,4})", raw)
    if m:
        y = int(m.group(1))
        if y < 100:
            y += 2000 if y < 80 else 1900
        return y
    return None


def calculate_age(birth_date_str):
    """생년월일 문자열 → 만 나이 + 일수"""
    if not birth_date_str:
        return None, None

    try:
        bd = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
        today = date.today()
        age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        # 마지막 생일로부터 경과 일수
        last_birthday = date(today.year, bd.month, bd.day)
        if last_birthday > today:
            last_birthday = date(today.year - 1, bd.month, bd.day)
        days = (today - last_birthday).days
        return age, days
    except:
        return None, None


# ============================================================
# 크롤링
# ============================================================
def fetch_profile(session, player_id, is_pitcher=False):
    """선수 프로필 페이지 가져오기"""
    url = (PITCHER_URL if is_pitcher else HITTER_URL) + str(player_id)
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return parse_profile(resp.text)
    except Exception as e:
        print(f"  [에러] {player_id}: {e}")
    return None


def get_all_player_ids(db_path):
    """DB에서 전체 Player_ID 및 타자/투수 구분"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    hitters = set()
    pitchers = set()
    player_names = {}

    for year in range(1982, 2026):
        try:
            cursor.execute(f"SELECT DISTINCT Player_ID, 선수명, 팀명 FROM kbo_hitting_basic1_{year}")
            for pid, name, team in cursor.fetchall():
                hitters.add(pid)
                player_names[pid] = (name, team)
        except:
            pass
        try:
            cursor.execute(f"SELECT DISTINCT Player_ID, 선수명, 팀명 FROM kbo_pitching_basic1_{year}")
            for pid, name, team in cursor.fetchall():
                pitchers.add(pid)
                if pid not in player_names:
                    player_names[pid] = (name, team)
        except:
            pass

    conn.close()

    # 분류: 투수 전용 → 투수 URL, 나머지 → 타자 URL 먼저 시도
    all_players = {}
    for pid in hitters | pitchers:
        name, team = player_names.get(pid, ("?", "?"))
        is_pitcher_only = pid in pitchers and pid not in hitters
        all_players[pid] = {
            "name": name,
            "team": team,
            "try_pitcher_first": is_pitcher_only,
        }

    return all_players


def main():
    print("=" * 50)
    print("  KBO 선수 프로필 크롤러")
    print("=" * 50)

    # 기존 결과 로드 (이어하기 지원)
    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"  기존 데이터 로드: {len(existing)}명")

    # Player_ID 수집
    players = get_all_player_ids(DB_PATH)
    print(f"  전체 선수: {len(players)}명")

    # 이미 크롤링된 선수 건너뛰기
    todo = {pid: info for pid, info in players.items() if pid not in existing}
    print(f"  신규 크롤링 대상: {len(todo)}명")
    print(f"  예상 시간: {len(todo) * REQUEST_DELAY / 60:.0f}분")

    if not todo:
        print("  모든 선수 크롤링 완료!")
        return

    session = requests.Session()
    done = 0
    failed = []

    for pid, info in todo.items():
        done += 1
        if done % 100 == 0:
            print(f"  진행: {done}/{len(todo)} ({done/len(todo)*100:.1f}%)")
            # 중간 저장
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

        # 투수 전용이면 투수 URL 먼저, 아니면 타자 URL 먼저
        if info["try_pitcher_first"]:
            profile = fetch_profile(session, pid, is_pitcher=True)
            if not profile:
                profile = fetch_profile(session, pid, is_pitcher=False)
                time.sleep(REQUEST_DELAY)
        else:
            profile = fetch_profile(session, pid, is_pitcher=False)
            if not profile:
                profile = fetch_profile(session, pid, is_pitcher=True)
                time.sleep(REQUEST_DELAY)

        if profile:
            profile["player_id"] = pid
            profile["db_name"] = info["name"]
            profile["db_team"] = info["team"]

            # 만 나이 계산
            age, days = calculate_age(profile.get("birth_date"))
            if age is not None:
                profile["age"] = age
                profile["age_days"] = days

            existing[pid] = profile
        else:
            failed.append(pid)

        time.sleep(REQUEST_DELAY)

    # 최종 저장
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"\n  완료: {len(existing)}명 저장")
    print(f"  실패: {len(failed)}명")
    if failed:
        print(f"  실패 ID: {failed[:20]}{'...' if len(failed) > 20 else ''}")
    print(f"  저장: {OUTPUT_PATH}")

    session.close()


if __name__ == "__main__":
    main()
