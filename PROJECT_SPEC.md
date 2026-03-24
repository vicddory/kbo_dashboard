# KBO 세이버메트릭스 대시보드 — 프로젝트 명세서 (PROJECT_SPEC.md)
# 최종 업데이트: 2026-03-23
# 이 파일을 AI(Claude/Cursor)에게 주면 프로젝트 전체 맥락을 이해하고 이어서 작업 가능

---

## 1. 프로젝트 개요

KBO 1982~2025년 전 시즌(44시즌) 세이버메트릭스 지표를 계산하고 시각화하는 대시보드.

- **기술 스택**: HTML + JavaScript (Chart.js) + Streamlit (추후 연동)
- **데이터**: JSON (database/data.json, 248KB)
- **타겟 유저**: 야구 데이터 분석에 관심 있는 한국 야구팬
- **제작자 응원팀**: KT 위즈 (브랜딩 반영됨)

---

## 2. 완료된 작업 (체크리스트)

### 데이터 수집
- [x] KBO 공식사이트 크롤러 구축 (ASP.NET AJAX UpdatePanel 파싱)
- [x] 선수 기록 DB 구축 (kbo_data.db, 478개 테이블)
  - hitting_basic1/basic2/detail1: 1982~2025 (각 44개 테이블)
  - pitching_basic1/basic2: 1982~2025 (각 44개 테이블)
  - 홈/원정 필터 데이터는 서버 문제로 전체와 동일 → 사용하지 않음
- [x] Statiz 홈/원정 데이터 수집 (콘솔 스크립팅으로 추출)
  - kbo_statiz_data_1982_1998_.xlsx
  - kbo_statiz_data_1999_2009_.xlsx
  - kbo_statiz_data_2010_2021_.xlsx
  - kbo_statiz_data_2022_2024_.xlsx

### 계산 완료
- [x] **파크팩터** (1982~2025, 44시즌)
  - 공식: `PF = H × T / ((T-1) × R + H)` (FanGraphs 방식)
  - H = 홈 RPG(양팀합산), R = 원정 RPG(양팀합산), T = 리그 팀 수
  - 1982~2024: Statiz 홈/원정 데이터로 계산
  - 2025: 직접 계산 (Statiz 캡쳐 데이터)
  - Statiz Single 파크팩터와 교차 검증 완료 (방향성 일치, ±20~60 범위 차이는 방법론 차이)
- [x] **ERA+** (1982~2025, 44시즌)
  - 공식: `ERA+ = 100 × (lgERA / ERA) × (PF / 100)` (현재 표준, Wikipedia/FanGraphs)
  - 규정이닝: 팀 최대 경기수 × 1.0
  - 검증: 1995 선동열 ERA+ 802, 2025 폰세 243.6 등 합리적
- [x] **OPS+** (1982~2025, 44시즌)
  - 공식: `OPS+ = 100 × (OBP/lgOBP + SLG/lgSLG - 1) / (PF/100)` (Baseball-Reference)
  - 규정타석: 팀 최대 경기수 × 3.1
  - 리그 평균 OBP/SLG는 DB에서 전체 합산으로 계산
  - 검증: 2015 테임즈 234.8, 2022 이정후 209.6 등 합리적

### 시각화
- [x] HTML 대시보드 기본 틀 (index.html)
- [x] 전체 데이터 JSON 추출 (database/data.json)
- [x] 색상 체계 확정

### 미완료
- [ ] **wRC+ 계산** — wOBA 가중치 산출 필요 (DB에 필요 데이터 모두 있음)
- [ ] **Streamlit 연동** — HTML을 Streamlit 내 컴포넌트로 임베드
- [ ] **선수 상세 페이지** — 커리어 곡선, 동포지션 비교
- [ ] **FA 적정가 모델** — wRC+/ERA+ 기반 가치 산출, aging curve
- [ ] **대시보드 고도화** — 반응형, 애니메이션, 검색 기능

---

## 3. 폴더 구조

```
kbo_dashboard/                    ← 프론트엔드 (배포용)
├── index.html                    ← 메인 SPA (4페이지: 리그환경/ERA+/OPS+/파크팩터)
├── database/
│   └── data.json                 ← 전체 데이터 (44시즌 ERA+/OPS+/파크팩터/리그환경)
└── image/
    ├── kt_logo_mono.png          ← KT 로고 (모노, 사이드바용)
    ├── kt_logo_full.png          ← KT 로고 (풀컬러, 푸터용)
    ├── mascot_batter.png         ← 타자 마스코트 (검정 빅, OPS+ 섹션)
    └── mascot_pitcher.png        ← 투수 마스코트 (흰색 빅, ERA+ 섹션)

kbo_scraper/                      ← 백엔드 (데이터 수집/계산)
├── main.py                       ← 크롤러 실행 진입점
├── kbo_config.py                 ← URL, ASP.NET 경로, 팀 코드 설정
├── kbo_crawler.py                ← ASP.NET AJAX 크롤러 (BaseScraper + KBOSeasonScraper)
├── kbo_storage.py                ← SQLite/CSV 저장소
├── data_parser.py                ← 데이터 파싱/정제
├── era_plus.py                   ← ERA+ 계산 모듈 ★
├── ops_plus.py                   ← OPS+ 계산 모듈 ★
├── wrc_plus.py                   ← wRC+ 계산 (미완성, MLB 가중치만 있음)
├── park_factor.py                ← 파크팩터 계산 (구버전, Statiz 데이터 사용으로 대체)
├── calc_park_factor_2025.py      ← 2025 파크팩터 직접 계산 스크립트
├── statiz_to_excel.py            ← Statiz 콘솔 데이터 → 엑셀 변환 도구
├── season_analyzer.py            ← 시즌 종합 분석
├── calculate_sabermetrics.py     ← 세이버메트릭스 일괄 계산
└── debug_*.py                    ← 디버그 스크립트 (무시 가능)
```

---

## 4. 데이터 구조

### 4-1. database/data.json 스키마
```json
{
  "league_env": [
    {"year": 1982, "lgERA": 3.88, "lgOBP": 0.338, "lgSLG": 0.39, "lgOPS": 0.728},
    ...  // 44개 (1982~2025)
  ],
  "era_plus": {
    "2025": [
      {"name": "폰세", "team": "한화", "era": 1.89, "ip": "180 2/3",
       "w": 17, "l": 1, "lgERA": 4.32, "pf": 106.5, "eraPlus": 243.6},
      ...  // 연도별 상위 20명
    ],
    "2024": [...],
    ...
  },
  "ops_plus": {
    "2025": [
      {"name": "송성문", "team": "키움", "avg": 0.315, "obp": 0.387,
       "slg": 0.53, "ops": 0.917, "hr": 26, "rbi": 90,
       "lgOBP": 0.338, "lgSLG": 0.389, "pf": 77.2, "opsPlus": 195.2},
      ...
    ],
    ...
  },
  "park_factors": {
    "2025": [
      {"team": "삼성", "pf": 117.4},
      {"team": "롯데", "pf": 112.7},
      ...  // PF 내림차순
    ],
    ...
  }
}
```

### 4-2. kbo_data.db (SQLite)

**사용하는 테이블** (130개):
| 테이블 패턴 | 개수 | 연도 | 주요 컬럼 |
|---|---|---|---|
| kbo_hitting_basic1_{연도} | 44 | 1982~2025 | Player_ID, 선수명, 팀명, AVG, G, PA, AB, R, H, 2B, 3B, HR, TB, RBI, SAC, SF |
| kbo_hitting_basic2_{연도} | 44 | 1982~2025 | Player_ID, 선수명, 팀명, AVG, BB, IBB, HBP, SO, GDP, SLG, OBP, OPS |
| kbo_hitting_detail1_{연도} | 44 | 1982~2025 | Player_ID, XBH, GO, AO, GO/AO, BB/K, ISOP, XR, GPA |
| kbo_pitching_basic1_{연도} | 44 | 1982~2025 | Player_ID, 선수명, 팀명, ERA, G, W, L, SV, HLD, IP, H, HR, BB, HBP, SO, R, ER, WHIP |
| kbo_pitching_basic2_{연도} | 44 | 1982~2025 | Player_ID, 선수명, 팀명 + 추가 투수 지표 |

**무시해도 되는 테이블** (348개):
- `kbo_hitting_basic1_홈/원정_{연도}`: 홈/원정 필터 미작동으로 전체와 동일
- `kbo_pitching_basic1_홈/원정_{연도}`: 같은 이유
- `kbo_team_hitting/pitching_전체/홈/원정_{연도}`: 같은 이유
- `kbo_fielding_basic`, `kbo_runner_basic`: 현재 미사용

### 4-3. 파크팩터 엑셀 (Statiz 원본)

각 파일 구조 동일:
- 시트: `{연도}_타격_홈`, `{연도}_타격_원정`, `{연도}_투구_홈`, `{연도}_투구_원정`, `파크팩터_{연도}`
- 팀명 매핑 이슈 (코드에서 처리됨):
  - 1985: DB `청보` ↔ PF `삼미/청보`
  - 2001: DB `KIA` ↔ PF `해태/KIA`
  - 2009: DB `히어로즈` ↔ PF `우리`
- 2025: Statiz 엑셀에 없음 → era_plus.py 내 PF_2025 딕셔너리로 하드코딩

---

## 5. 계산 공식 (출처 포함)

### ERA+ (출처: Wikipedia "Adjusted ERA+", FanGraphs Sabermetrics Library)
```
ERA+ = 100 × (lgERA / ERA) × (PF / 100)
```
- lgERA: 해당 연도 리그 전체 ER×9/IP
- PF: 해당 팀의 파크팩터 (100 기준)
- 100 = 리그 평균, 150 = 평균보다 50% 우수

### OPS+ (출처: Baseball-Reference)
```
OPS+ = 100 × (OBP/lgOBP + SLG/lgSLG - 1) / (PF/100)
```
- lgOBP: (리그H + 리그BB + 리그HBP) / (리그AB + 리그BB + 리그HBP + 리그SF)
- lgSLG: 리그TB / 리그AB
- 100 = 리그 평균

### 파크팩터 (출처: FanGraphs "Park Factors - 5 Year Regressed")
```
raw PF = H × T / ((T-1) × R + H)
```
- H: 홈 경기 RPG (양팀 합산 = 타격R + 투수R) / 홈 경기수
- R: 원정 경기 RPG (양팀 합산) / 원정 경기수
- T: 리그 팀 수 (6~10, 연도별 다름)

### wOBA (미구현, 다음 단계)
```
wOBA = (wBB×BB + wHBP×HBP + w1B×1B + w2B×2B + w3B×3B + wHR×HR) / (PA - IBB - SH)
```
- 가중치 산출 방법 2가지:
  1. Run Expectancy Matrix에서 직접 산출 (플레이바이플레이 데이터 필요 → 없음)
  2. FanGraphs Basic wOBA 고정 가중치: `.7×(BB+HBP) + .9×1B + 1.25×2B + 1.6×3B + 2×HR) / PA`
- 1B = H - 2B - 3B - HR (DB에서 계산)
- DB에 필요 데이터 모두 있음 (hitting_basic1 + hitting_basic2)

### wRC+ (미구현)
```
wRC+ = (((wRAA/PA + lgR/PA) + (lgR/PA - PF × lgR/PA)) / (lgwRC/PA)) × 100
```

---

## 6. 색상 체계 (확정)

### 6-1. UI 기본 (Perplexity 제안 기반, GitHub Dark 참고)
| 요소 | 라이트모드 | 다크모드 |
|---|---|---|
| 배경 | #F4F6F9 | #0D1117 |
| 카드 | #FFFFFF | #161B22 |
| 테두리 | #DDE1E7 | #30363D |
| 본문 텍스트 | #1A1D23 | #E6EDF3 |
| 보조 텍스트 | #5A6275 | #8B949E |
| Primary | #1565C0 | #58A6FF |
| Accent | #D6604D | #FF7B6B |

### 6-2. 차트 (ColorBrewer RdBu 기반, 색각 안전)
| 용도 | HEX |
|---|---|
| ERA 라인 | #2166AC |
| OPS 라인 | #D6604D |
| ERA+ 막대 | #4393C3 |
| OPS+ 막대 | #F4A582 |
| 시리즈5 (wRC+) | #4DAF4A |
| 시리즈6 (FA) | #984EA3 |

### 6-3. 등급 배지 (ERA+/OPS+ 테이블)
| 등급 | 기준 | HEX | 다크모드 |
|---|---|---|---|
| 엘리트 | 200+ | #7B2D8B | rgba(123,45,139,0.25) |
| 우수 | 150~199 | #1A6B3C | rgba(26,107,60,0.25) |
| 평균 이상 | 120~149 | #1565C0 | rgba(21,101,192,0.25) |
| 평균 | 100~119 | #5A6275 | rgba(90,98,117,0.20) |
| 평균 이하 | <100 | #C62828 | rgba(198,40,40,0.20) |

### 6-4. 파크팩터 (발산형 스케일)
| 구간 | HEX | 의미 |
|---|---|---|
| 115+ | #B2182B | 극단 타자친화 |
| 105~115 | #EF8A62 | 타자친화 |
| 95~105 | #F7F7F7 (다크:#2D333B) | 중립 |
| 85~95 | #67A9CF | 투수친화 |
| ~85 | #2166AC | 극단 투수친화 |

### 6-5. KT 위즈 브랜딩 (응원팀)
| 요소 | HEX | 적용 위치 |
|---|---|---|
| 블랙 | #2B2B2B | 사이드바 배경 |
| 레드 | #E2001A | 사이드바 보더, 활성 탭, 푸터 악센트 |
| 실버 | #C0C0C0 | 사이드바 보조 텍스트 |

### 6-6. KBO 팀 컬러 (채도 조정)
```
KIA: #C8102E, 삼성: #1A4B9B, LG: #C41230, 두산: #131230
KT: #2B2B2B, SSG: #CE0E2D, NC: #1B4F9C, 롯데: #D0021B
한화: #E87722, 키움: #570514
```

---

## 7. 마스코트 배치 규칙

| 위치 | 이미지 | 설명 |
|---|---|---|
| ERA+ 섹션 헤더 | mascot_pitcher.png | 44px 작은 아이콘 |
| ERA+ 섹션 우하단 | mascot_pitcher.png | 100px, opacity 12%, 장식용 |
| OPS+ 섹션 헤더 | mascot_batter.png | 44px 작은 아이콘 |
| OPS+ 섹션 우하단 | mascot_batter.png | 100px, opacity 12%, 장식용 |

- **투수 마스코트 (흰색 빅)**: 6포즈 중 3번째(오른쪽 상단, 공 여러개 물고 있는 것) 제외
- **타자 마스코트 (검정 빅)**: 6포즈 모두 사용 가능
- 이미지 경로: `image/` 폴더 (파일명은 추후 변경 가능)

---

## 8. 현재 HTML 구조 (index.html)

### SPA 4페이지 (네비게이션으로 전환)
1. **리그 환경** (`pg-dashboard`): 요약카드 4개 + ERA/OPS 라인차트 + ERA+/OPS+ 1위 바차트
2. **ERA+ 랭킹** (`pg-era`): 연도 셀렉트(1982~2025) + 팀 필터 + 상위 20명 테이블 + 등급 배지
3. **OPS+ 랭킹** (`pg-ops`): 동일 구조
4. **파크팩터** (`pg-pf`): 연도 셀렉트 + 양방향 바차트 (블루↔레드)

### 데이터 로딩
- `fetch('database/data.json')` → 전역 변수 `D`에 저장
- 모든 렌더링 함수가 `D`를 참조
- 연도 변경 시 `renderEra()`, `renderOps()`, `renderPf()` 호출

### 다크/라이트 모드
- `<html data-theme="dark">` 기본
- CSS 변수로 전환, Chart.js는 테마 변경 시 재생성

---

## 9. 다음 작업 우선순위

1. **wRC+ 계산 구현** — Basic wOBA 고정 가중치로 시작
2. **대시보드에 wRC+ 탭 추가**
3. **선수 검색/상세 페이지** — 이름 검색 → 커리어 곡선
4. **Streamlit 래퍼** — HTML을 streamlit-components로 임베드
5. **FA 적정가 모델**

---

## 10. 알려진 이슈

1. **IP(이닝) 파싱**: KBO 사이트는 "6 2/3" 형식, era_plus.py의 `parse_ip()` 함수로 처리
2. **팀명 변경 이력**: 해태→KIA, OB→두산, 빙그레→한화 등 — 파크팩터 매칭 시 TEAM_NAME_MAP 딕셔너리 사용
3. **2025 파크팩터**: Statiz에 없어서 era_plus.py 내 PF_2025 딕셔너리로 하드코딩
4. **홈/원정 필터 미작동**: KBO 사이트 선수 기록 페이지의 경기상황별 필터가 re-GET 시 리셋됨 → Statiz 데이터로 대체

---

## 11. 핵심 코드 실행 방법

### ERA+ 계산
```bash
cd [파크팩터 엑셀이 있는 폴더]
python era_plus.py
# 파크팩터 엑셀 4개 + kbo_data.db 필요
```

### OPS+ 계산
```bash
cd [파크팩터 엑셀이 있는 폴더]
python ops_plus.py
# 같은 파일 필요
```

### data.json 재생성
```python
# era_plus.py, ops_plus.py의 calculate 함수를 호출해서 JSON 생성
# 현재 별도 스크립트 없음 → 이 세션에서 인라인 코드로 실행했음
# 추후 gen_data_json.py로 분리 필요
```

### 대시보드 실행
```bash
cd kbo_dashboard
python -m http.server 8000
# 브라우저에서 http://localhost:8000
```

### Statiz 데이터 추가 (새 시즌)
```bash
cd [kbo_scraper 폴더]
python statiz_to_excel.py
# 연도 입력 → a(4개 연속) → Statiz 콘솔 데이터 붙여넣기
```
