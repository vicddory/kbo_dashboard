"""
KBO 크롤러 설정 파일
- URL, 카테고리, 크롤링 옵션 등을 중앙 관리
- 새로운 데이터 소스 추가 시 이 파일만 수정하면 됨

데이터 소스 정책:
    - KBO 공식 홈페이지: 클래식 스탯(1차 기록) 수집 전용
    - 세이버메트릭스 지표(wRC+, ERA+, 파크팩터 등):
      FanGraphs / Baseball-Reference 공개 공식 기반으로 자체 계산
    - 스탯티즈 등 외부 세이버 사이트의 보정 지표는 참고하지 않음
"""

import logging
from datetime import datetime

# ============================================================
# 로깅 설정
# ============================================================
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ============================================================
# 크롤링 공통 설정
# ============================================================
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 2
MAX_RETRIES = 3
RETRY_DELAY = 5

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ============================================================
# KBO 사이트 기본 정보
# ============================================================
CURRENT_YEAR = datetime.now().year
KBO_BASE_URL = "https://www.koreabaseball.com"

# ASP.NET 컨트롤 경로 (실제 HTML에서 확인됨)
ASPNET = {
    "pager_prefix": "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager",
    "pager_first": "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnFirst",
    "pager_last": "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnLast",
    # 페이지 번호 버튼: btnNo1, btnNo2, ... (PostBack 시 __EVENTTARGET에 사용)
    "pager_btn_template": "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnNo{num}",
    # 드롭다운 (연도, 시리즈, 팀 선택 등)
    "season_dropdown": "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeason$ddlSeason",
    "series_dropdown": "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeries$ddlSeries",
    "team_dropdown": "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlTeam$ddlTeam",
    # 경기상황 필터 (홈/방문별 등)
    "situation_dropdown": "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSituation$ddlSituation",
    "situation_detail_dropdown": "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSituationDetail$ddlSituationDetail",
}

# 홈/원정 필터 값 (실제 HTML에서 확인됨)
HOME_AWAY_FILTER = {
    "situation_value": "HOMEAYAY_SC",   # 경기상황별1에서 "홈/방문별" 선택
    "home_value": "B",                  # 경기상황별2에서 "홈"
    "away_value": "T",                  # 경기상황별2에서 "방문"
}

# KBO 팀 목록 (실제 HTML에서 확인된 드롭다운 value + 활동 연도 + 정렬 순서)
# years: (시작연도, 종료연도) — None이면 현재까지 활동 중
# order: 정렬 순서 (낮을수록 먼저)
# 표기는 KBO 사이트 드롭다운 기준 (코드는 전 시기 동일)
KBO_TEAMS = {
    "KT":   {"code": "KT", "years": (2015, None),  "order": 1},
    "삼성":  {"code": "SS", "years": (1982, None),  "order": 10},
    "현대":  {"code": "HD", "years": (1982, 2007),  "order": 20},   # 삼미(82-84)→청보(85-87)→태평양(88-95)→현대(96-07)
    "KIA":  {"code": "HT", "years": (1982, None),  "order": 30},   # 해태(82-00)→KIA(01~)
    "두산":  {"code": "OB", "years": (1982, None),  "order": 40},   # OB(82-98)→두산(99~)
    "쌍방울": {"code": "SB", "years": (1991, 1999), "order": 50},
    "SSG":  {"code": "SK", "years": (2000, None),  "order": 50},   # SK(00-20)→SSG(21~)
    "한화":  {"code": "HH", "years": (1986, None),  "order": 60},   # 빙그레(86-93)→한화(94~)
    "롯데":  {"code": "LT", "years": (1982, None),  "order": 70},
    "LG":   {"code": "LG", "years": (1982, None),  "order": 80},   # MBC(82-89)→LG(90~)
    "키움":  {"code": "WO", "years": (2008, None),  "order": 20},   # 우리(08)→히어로즈(09)→넥센(10-18)→키움(19~)
    "NC":   {"code": "NC", "years": (2013, None),  "order": 90},
}


def get_teams_for_year(year: int) -> dict:
    """해당 연도에 존재한 팀만 반환 (order 순서로 정렬)"""
    filtered = {}
    for name, info in KBO_TEAMS.items():
        start, end = info["years"]
        if start <= year and (end is None or year <= end):
            filtered[name] = info

    # order 기준 정렬
    sorted_teams = dict(
        sorted(filtered.items(), key=lambda x: x[1]["order"])
    )
    return {name: info["code"] for name, info in sorted_teams.items()}

# ============================================================
# 선수 기록 카테고리
# ============================================================
# 수집 전략:
#   1) 팀 필터를 10개 팀 순회 → 규정 미달 선수까지 확보
#   2) 각 팀 내에서 전체 페이지 순회 (ASP.NET PostBack)
#   3) Basic1 + Basic2 + Detail1 을 세트로 수집 → Player_ID로 조인
#
# Detail 페이지에 wRC+ 계산 필수 항목 (BB, IBB, HBP, SO 등) 포함

KBO_HITTING_PAGES = {
    "hitting_basic1": {
        "url": f"{KBO_BASE_URL}/Record/Player/HitterBasic/Basic1.aspx",
        "description": "타자 기본 1 (AVG, G, PA, AB, R, H, 2B, 3B, HR, TB, RBI, SAC, SF)",
    },
    "hitting_basic2": {
        "url": f"{KBO_BASE_URL}/Record/Player/HitterBasic/Basic2.aspx",
        "entry_url": f"{KBO_BASE_URL}/Record/Player/HitterBasic/Basic1.aspx",
        "description": "타자 기본 2 (SLG, OBP, OPS, BB, HBP 등) — Basic1 경유 필요",
    },
    "hitting_detail1": {
        "url": f"{KBO_BASE_URL}/Record/Player/HitterBasic/Detail1.aspx",
        "entry_url": f"{KBO_BASE_URL}/Record/Player/HitterBasic/Basic1.aspx",
        "description": "타자 세부 1 (BB, IBB, HBP, SO, GDP 등) — Basic1 경유 필요",
    },
}

KBO_PITCHING_PAGES = {
    "pitching_basic1": {
        "url": f"{KBO_BASE_URL}/Record/Player/PitcherBasic/Basic1.aspx",
        "description": "투수 기본 1 (ERA, G, W, L, SV, IP, H, HR, SO 등)",
    },
    "pitching_basic2": {
        "url": f"{KBO_BASE_URL}/Record/Player/PitcherBasic/Basic2.aspx",
        "entry_url": f"{KBO_BASE_URL}/Record/Player/PitcherBasic/Basic1.aspx",
        "description": "투수 기본 2 (WHIP, 피안타율 등) — Basic1 경유 필요",
    },
    "pitching_detail1": {
        "url": f"{KBO_BASE_URL}/Record/Player/PitcherBasic/Detail1.aspx",
        "entry_url": f"{KBO_BASE_URL}/Record/Player/PitcherBasic/Basic1.aspx",
        "description": "투수 세부 1 (ER, BB, IBB, HBP 등) — Basic1 경유 필요",
    },
}

KBO_OTHER_PAGES = {
    "fielding_basic": {
        "url": f"{KBO_BASE_URL}/Record/Player/Defense/Basic.aspx",
        "description": "수비 기본 기록",
    },
    "runner_basic": {
        "url": f"{KBO_BASE_URL}/Record/Player/Runner/Basic.aspx",
        "description": "주루 기본 기록",
    },
}

# 전체 선수 기록 카테고리 통합
KBO_PLAYER_CATEGORIES = {
    **KBO_HITTING_PAGES,
    **KBO_PITCHING_PAGES,
    **KBO_OTHER_PAGES,
}

# ============================================================
# 팀 기록 카테고리 (파크팩터 계산용)
# ============================================================
# 홈/원정 필터를 적용하여 팀별 홈 득점/실점, 원정 득점/실점 수집
# → park_factor.py에서 파크팩터 산출

KBO_TEAM_RECORD_PAGES = {
    "team_hitting": {
        "url": f"{KBO_BASE_URL}/Record/Team/Hitter/BasicOld.aspx",
        "description": "팀 타격 기록 (홈/원정 분리 수집용)",
    },
    "team_pitching": {
        "url": f"{KBO_BASE_URL}/Record/Team/Pitcher/BasicOld.aspx",
        "description": "팀 투수 기록 (홈/원정 분리 수집용)",
    },
}

# ============================================================
# 저장소 설정
# ============================================================
SQLITE_DB_PATH = "kbo_data.db"
CSV_OUTPUT_DIR = "csv_output"

# ============================================================
# 확장용 플레이스홀더
# ============================================================
# KBO_GAMELOG_PAGES = { ... }  # 경기별 데이터 (WPA 계산용)
