"""
크롤러 모듈 (v2)

주요 변경점:
    - 팀별 순회 크롤링으로 규정 미달 선수까지 수집
    - 실제 KBO HTML에서 확인된 ASP.NET 컨트롤 경로 사용
    - 팀 기록 홈/원정 분리 수집 (파크팩터 계산용)
    - Detail 페이지 수집 지원 (wRC+ 필수 항목)
"""

import re
import time
import logging
import urllib.parse
from abc import ABC, abstractmethod
from typing import Optional

import requests
from bs4 import BeautifulSoup

from kbo_config import (
    DEFAULT_HEADERS,
    REQUEST_TIMEOUT,
    REQUEST_DELAY,
    MAX_RETRIES,
    RETRY_DELAY,
    ASPNET,
    CURRENT_YEAR,
    KBO_TEAMS,
    HOME_AWAY_FILTER,
    get_teams_for_year,
)

logger = logging.getLogger(__name__)


# ============================================================
# 베이스 크롤러
# ============================================================
class BaseScraper(ABC):
    """
    모든 크롤러의 부모 클래스.
    새 데이터 소스 추가 시 상속하여 fetch_page/parse_page 구현.
    """

    def __init__(self, headers: Optional[dict] = None):
        self.session = requests.Session()
        self.session.headers.update(headers or DEFAULT_HEADERS)
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def fetch_page(self, url: str, **kwargs) -> Optional[str]:
        pass

    @abstractmethod
    def parse_page(self, html: str, **kwargs) -> dict:
        pass

    def _request_with_retry(self, method, url, max_retries=MAX_RETRIES, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.exceptions.Timeout:
                self.logger.warning(f"타임아웃 ({attempt}/{max_retries}): {url}")
            except requests.exceptions.HTTPError as e:
                self.logger.warning(f"HTTP {e.response.status_code} ({attempt}/{max_retries}): {url}")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"요청 실패 ({attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(RETRY_DELAY * attempt)
        self.logger.error(f"최대 재시도 초과: {url}")
        return None

    def close(self):
        self.session.close()


# ============================================================
# KBO 시즌 크롤러
# ============================================================
class KBOSeasonScraper(BaseScraper):
    """
    KBO 공식 사이트에서 시즌 기록을 크롤링한다.
    팀별 순회 + ASP.NET PostBack 페이지네이션.
    """

    def fetch_page(self, url: str, referer: Optional[str] = None, **kwargs) -> Optional[str]:
        headers = {"Referer": referer} if referer else {}
        resp = self._request_with_retry("GET", url, headers=headers)
        return resp.text if resp else None

    def _extract_aspnet_fields(self, soup: BeautifulSoup) -> dict:
        """ASP.NET 폼 필드 전체 추출 (히든 필드 + 드롭다운 현재값)"""
        fields = {}

        # 1) 히든 필드 (__VIEWSTATE, __EVENTVALIDATION 등)
        for hidden in soup.find_all("input", {"type": "hidden"}):
            name = hidden.get("name", "")
            if name:
                fields[name] = hidden.get("value", "")

        # 2) 모든 select 드롭다운의 현재 선택값
        for select in soup.find_all("select"):
            name = select.get("name", "")
            if not name:
                continue
            selected = select.find("option", selected=True)
            if selected:
                fields[name] = selected.get("value", "")
            else:
                first = select.find("option")
                if first:
                    fields[name] = first.get("value", "")

        return fields

    def _get_total_pages(self, soup: BeautifulSoup) -> int:
        """페이지네이션에서 총 페이지 수 추출"""
        paging = soup.find("div", class_="paging")
        if not paging:
            return 1

        page_numbers = []

        # btnNo1, btnNo2, ... 링크에서 번호 추출
        for a_tag in paging.find_all("a"):
            href = a_tag.get("href", "")
            match = re.search(r"btnNo(\d+)", href)
            if match:
                page_numbers.append(int(match.group(1)))

        # 현재 페이지 (span 태그)
        for span in paging.find_all("span"):
            try:
                page_numbers.append(int(span.text.strip()))
            except ValueError:
                continue

        # 마지막 페이지 버튼 (btnLast)
        last_link = paging.find("a", href=re.compile(r"btnLast"))
        if last_link:
            # btnLast가 있으면 더 많은 페이지가 있다는 뜻
            # 실제 마지막 페이지 번호는 btnLast를 눌러봐야 알 수 있음
            # 일단 현재 보이는 최대 + 추가 페이지 가정
            pass

        return max(page_numbers) if page_numbers else 1

    def _post_aspnet(self, url: str, soup: BeautifulSoup,
                     event_target: str, event_argument: str = "",
                     extra_fields: Optional[dict] = None) -> Optional[str]:
        """
        ASP.NET PostBack 요청 (AJAX UpdatePanel 지원).
        KBO 사이트는 ScriptManager + UpdatePanel을 사용하므로
        partial postback 헤더와 ScriptManager 필드를 포함해야 함.

        중요: Referer 헤더와 ?sort=HRA_RT 쿼리 파라미터가 모두 있어야
        서버 세션 상태가 정상적으로 업데이트된다 (브라우저 동작 재현).
        """
        form_data = self._extract_aspnet_fields(soup)
        form_data["__EVENTTARGET"] = event_target
        form_data["__EVENTARGUMENT"] = event_argument

        # ASP.NET AJAX ScriptManager 필드 (실제 브라우저 요청에서 확인)
        sm_key = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$smData"
        sm_value = (
            "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$udpContent|"
            + event_target
        )
        form_data[sm_key] = sm_value
        form_data["__ASYNCPOST"] = "true"

        if extra_fields:
            form_data.update(extra_fields)

        # AJAX 헤더 + Referer (세션 상태 전파에 필수)
        ajax_headers = {
            "X-Requested-With": "XMLHttpRequest",
            "X-MicrosoftAjax": "Delta=true",
            "Referer": url,
        }

        # ?sort=HRA_RT 쿼리 파라미터 추가 (세션 상태 전파에 필수)
        post_url = url if "?" in url else url + "?sort=HRA_RT"

        resp = self._request_with_retry("POST", post_url, data=form_data, headers=ajax_headers)
        if not resp:
            return None

        text = resp.text

        # AJAX pageRedirect 감지 (에러 페이지 리다이렉트)
        if "|pageRedirect|" in text[:500]:
            self.logger.warning(f"AJAX 에러: pageRedirect 감지")
            return None

        # AJAX partial response인 경우 HTML + 히든 필드 추출
        if text.startswith("1|#||") or "|updatePanel|" in text[:500]:
            html_part = self._parse_ajax_response(text)
            if html_part:
                return html_part

        return text

    def _parse_ajax_response(self, ajax_response: str) -> Optional[str]:
        """
        ASP.NET AJAX partial response를 파싱한다.

        응답 형식:
            length|type|id|content|length|type|id|content|...

        type별 처리:
            - updatePanel: HTML 콘텐츠
            - hiddenField: __VIEWSTATE, __EVENTVALIDATION 등

        HTML과 히든 필드를 합쳐서 완전한 HTML 문서로 반환.
        """
        html_content = ""
        hidden_fields = []

        try:
            # updatePanel에서 HTML 추출 (length 기반)
            marker = "|updatePanel|"
            idx = ajax_response.find(marker)
            if idx >= 0:
                # marker 앞의 length 값 찾기
                pre = ajax_response[:idx]
                # 맨 마지막 | 이후의 숫자가 length
                last_pipe = pre.rfind("|")
                if last_pipe >= 0:
                    length_str = pre[last_pipe + 1:]
                else:
                    length_str = pre
                length = int(length_str)

                # panel ID 찾기: updatePanel| 이후 다음 | 까지
                after_marker = ajax_response[idx + len(marker):]
                pipe_pos = after_marker.find("|")
                if pipe_pos >= 0:
                    content_start = idx + len(marker) + pipe_pos + 1
                    html_content = ajax_response[content_start:content_start + length]

            # hiddenField에서 __VIEWSTATE 등 추출
            # 실제 KBO 응답 형식: |valueLength|hiddenField|name|value (value가 valueLength 바이트)
            pos = 0
            while True:
                hf_marker = "|hiddenField|"
                hf_idx = ajax_response.find(hf_marker, pos)
                if hf_idx < 0:
                    break

                after_hf_start = hf_idx + len(hf_marker)
                after_hf = ajax_response[after_hf_start:]

                # 형식: valueLength|fieldName|value (value는 valueLength 문자)
                pipe1 = after_hf.find("|")
                if pipe1 < 0:
                    break
                try:
                    value_length = int(after_hf[:pipe1])
                except ValueError:
                    break

                rest = after_hf[pipe1 + 1:]
                pipe2 = rest.find("|")
                if pipe2 < 0:
                    break
                field_name = rest[:pipe2]

                # value 시작: after_hf_start + (pipe1+1) + (pipe2+1)
                value_start = after_hf_start + (pipe1 + 1) + (pipe2 + 1)
                field_value = ajax_response[value_start : value_start + value_length]
                # HTML 속성 내 특수문자 이스케이프
                field_value_escaped = (
                    field_value.replace("&", "&amp;").replace('"', "&quot;")
                    .replace("<", "&lt;").replace(">", "&gt;")
                )

                hidden_fields.append(
                    f'<input type="hidden" name="{field_name}" value="{field_value_escaped}" />'
                )

                pos = value_start + value_length

        except (ValueError, IndexError) as e:
            self.logger.debug(f"AJAX 응답 파싱 실패: {e}")
            return None

        if not html_content:
            return None

        # HTML + 히든 필드를 합쳐서 완전한 문서 생성
        hidden_html = "\n".join(hidden_fields)
        return f"<html><body>\n{html_content}\n{hidden_html}\n</body></html>"

    def _post_for_page(self, url: str, soup: BeautifulSoup, page_num: int) -> Optional[str]:
        """특정 페이지로 이동 (PostBack)"""
        # KBO 사이트는 btnNo1, btnNo2, ... 형태
        event_target = ASPNET["pager_btn_template"].format(num=page_num)
        return self._post_aspnet(url, soup, event_target)

    def _post_for_team(self, url: str, soup: BeautifulSoup, team_name: str) -> Optional[str]:
        """팀 드롭다운 변경 (PostBack)"""
        extra = {ASPNET["team_dropdown"]: team_name}
        return self._post_aspnet(url, soup, ASPNET["team_dropdown"], extra_fields=extra)

    def _post_for_year(self, url: str, soup: BeautifulSoup, year: int,
                       series: str = "0") -> Optional[str]:
        """
        연도 드롭다운 변경 (PostBack).
        시리즈도 동시에 설정한다 (기본값: 0=정규시즌).
        """
        extra = {
            ASPNET["season_dropdown"]: str(year),
            ASPNET["series_dropdown"]: series,
        }
        return self._post_aspnet(url, soup, ASPNET["season_dropdown"], extra_fields=extra)

    def _post_for_series(self, url: str, soup: BeautifulSoup,
                         series: str = "0") -> Optional[str]:
        """시리즈 드롭다운 변경 (정규시즌=0, 시범경기=1 등)"""
        extra = {ASPNET["series_dropdown"]: series}
        return self._post_aspnet(url, soup, ASPNET["series_dropdown"], extra_fields=extra)

    def _setup_year_on_page(self, url: str, soup: BeautifulSoup,
                            year: int) -> Optional[BeautifulSoup]:
        """
        페이지에서 연도+정규시즌을 설정한다.
        초기 상태가 시범경기(2002~)일 수 있으므로:
          1) 시리즈=0(정규시즌) AJAX POST (연도 목록 확장)
          2) 다시 GET (정상 HTML 확보)
          3) 연도 AJAX POST (시리즈=0 동시)
          4) 다시 GET (정상 HTML 확보)
        """
        # Step 1: 시리즈를 정규시즌으로 변경
        self._post_for_series(url, soup, "0")

        # Step 2: 다시 GET (정규시즌 상태의 정상 HTML)
        html = self.fetch_page(url, referer=url)
        if not html:
            return None
        soup2 = self.parse_page(html)["soup"]

        # Step 3: 연도 변경 (시리즈=0 동시)
        self._post_for_year(url, soup2, year, series="0")

        # Step 4: 다시 GET (연도+정규시즌 설정된 정상 HTML)
        html = self.fetch_page(url, referer=url)
        if not html:
            return None
        return self.parse_page(html)["soup"]

    def _post_for_situation(self, url: str, soup: BeautifulSoup,
                            situation_value: str) -> Optional[str]:
        """경기상황별1 드롭다운 변경 (예: 홈/방문별)"""
        ctrl = ASPNET["situation_dropdown"]
        extra = {ctrl: situation_value}
        return self._post_aspnet(url, soup, ctrl, extra_fields=extra)

    def _post_for_situation_detail(self, url: str, soup: BeautifulSoup,
                                   detail_value: str) -> Optional[str]:
        """경기상황별2 드롭다운 변경 (예: 홈=B, 방문=T)"""
        ctrl = ASPNET["situation_detail_dropdown"]
        # 경기상황별1의 현재 값도 유지해야 하므로 situation 드롭다운도 같이 전송
        extra = {
            ASPNET["situation_dropdown"]: HOME_AWAY_FILTER["situation_value"],
            ctrl: detail_value,
        }
        return self._post_aspnet(url, soup, ctrl, extra_fields=extra)

    def parse_page(self, html: str, **kwargs) -> dict:
        """HTML 테이블 파싱"""
        soup = BeautifulSoup(html, "html.parser")

        # KBO 사이트의 기록 테이블 탐색
        table = (
            soup.find("table", class_="tData01")
            or soup.find("table", class_="tData")
            or soup.find("table", class_="t_list")
            or soup.find("table", class_="tEx")
        )

        if not table:
            self.logger.warning("테이블을 찾을 수 없음")
            return {"headers": [], "rows": [], "total_pages": 0, "soup": soup}

        # 헤더 — 선수 기록이면 Player_ID 추가, 팀 기록이면 그대로
        raw_headers = [th.text.strip() for th in table.find_all("th") if th.text.strip()]

        # 선수 기록인지 팀 기록인지 판별 (팀 기록은 "선수명" 헤더가 없음)
        is_player_record = "선수명" in raw_headers
        if is_player_record:
            headers = ["Player_ID"] + raw_headers
        else:
            headers = raw_headers

        # 데이터 행
        rows = []
        tbody = table.find("tbody")
        if not tbody:
            return {"headers": headers, "rows": [], "total_pages": 0, "soup": soup}

        for tr in tbody.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) <= 1:
                continue

            player_id = ""
            row_data = []

            for td in cells:
                a_tag = td.find("a")
                if a_tag and "href" in a_tag.attrs:
                    href = a_tag["href"]
                    parsed = urllib.parse.urlparse(href)
                    params = urllib.parse.parse_qs(parsed.query)
                    if "playerId" in params:
                        player_id = params["playerId"][0]
                row_data.append(td.text.strip())

            if is_player_record:
                row_data.insert(0, player_id)

            if len(row_data) == len(headers):
                rows.append(row_data)
            else:
                self.logger.debug(
                    f"컬럼 불일치 (기대 {len(headers)}, 실제 {len(row_data)}), 스킵"
                )

        total_pages = self._get_total_pages(soup)
        return {"headers": headers, "rows": rows, "total_pages": total_pages, "soup": soup}

    def _scrape_all_pages(self, url: str, soup: BeautifulSoup,
                          initial_result: dict, label: str) -> list:
        """현재 상태에서 모든 페이지의 행을 수집"""
        all_rows = list(initial_result["rows"])
        total_pages = initial_result["total_pages"]

        for page in range(2, total_pages + 1):
            self.logger.info(f"  [{label}] {page}/{total_pages} 페이지...")
            html = self._post_for_page(url, initial_result["soup"], page)
            if not html:
                self.logger.warning(f"  [{label}] {page}페이지 실패, 건너뜀")
                continue
            result = self.parse_page(html)
            all_rows.extend(result["rows"])
            initial_result["soup"] = result["soup"]  # 다음 POST용 갱신
            time.sleep(REQUEST_DELAY)

        return all_rows

    # ============================================================
    # 공개 API: 팀별 순회 크롤링
    # ============================================================

    def scrape_category_by_team(
        self, url: str, category: str, year: Optional[int] = None,
        entry_url: Optional[str] = None,
        team_filter: Optional[str] = None,
        home_away: Optional[str] = None,
    ) -> dict:
        """
        팀 필터를 순회하며 전체 선수 기록을 수집한다.

        Args:
            url: 카테고리 URL (실제 데이터 페이지)
            category: 카테고리명
            year: 시즌 연도 (None이면 현재 시즌)
            entry_url: 세션 초기화용 URL (Basic2 등은 Basic1을 먼저
                       GET해야 리다이렉트 없이 접근 가능)
            team_filter: 특정 팀만 수집 (팀 이름, 예: "현대", "KT")
            home_away: "홈" | "원정" — 홈/원정 필터 적용

        Returns:
            {"headers": [...], "rows": [[...], ...]}
        """
        ha_label = f" ({home_away})" if home_away else ""
        self.logger.info(f"[{category}] 팀별 순회 크롤링 시작 (연도: {year or '현재'}{ha_label})")

        # entry_url 경유 전략:
        #   1) entry_url GET → 세션 쿠키 확보
        #   2) url GET → 리다이렉트 없이 접근
        #   3) url에서 연도/팀 POST → 데이터 수집
        # (연도/팀 상태는 URL별로 관리되므로 url에서 직접 POST해야 함)

        # 헤더 확보를 위한 초기 접근
        if entry_url:
            self.logger.info(f"[{category}] 세션 초기화: {entry_url}")
            entry_html = self.fetch_page(entry_url)
            if not entry_html:
                self.logger.error(f"[{category}] entry 페이지 로드 실패")
                return {"headers": [], "rows": []}

            if year is not None:
                entry_result = self.parse_page(entry_html)
                self._setup_year_on_page(entry_url, entry_result["soup"], year)

            html = self.fetch_page(url, referer=entry_url)
            if not html:
                self.logger.error(f"[{category}] 데이터 페이지 로드 실패")
                return {"headers": [], "rows": []}
            result = self.parse_page(html)
        else:
            html = self.fetch_page(url)
            if not html:
                self.logger.error(f"[{category}] 데이터 페이지 로드 실패")
                return {"headers": [], "rows": []}
            result = self.parse_page(html)

            if year is not None:
                soup_ready = self._setup_year_on_page(url, result["soup"], year)
                if not soup_ready:
                    self.logger.error(f"[{category}] 연도 변경 실패")
                    return {"headers": [], "rows": []}
                result = {"headers": result["headers"], "rows": [], "soup": soup_ready}

        all_headers = result["headers"]
        all_rows = []
        seen_player_ids = set()

        # 해당 연도에 존재한 팀만 순회
        teams = get_teams_for_year(year) if year else get_teams_for_year(CURRENT_YEAR)

        # 특정 팀만 수집
        if team_filter:
            if team_filter in teams:
                teams = {team_filter: teams[team_filter]}
            else:
                self.logger.error(f"[{category}] '{team_filter}'은(는) {year}년에 존재하지 않는 팀")
                return {"headers": all_headers, "rows": []}

        for team_name, team_code in teams.items():
            self.logger.info(f"[{category}] 팀: {team_name} ({team_code})")

            if entry_url:
                # entry_url 경유 방식 (Basic2, Detail1 등):
                #   1) entry_url(Basic1) GET → 세션 초기화
                #   2) entry_url(Basic1)에서 연도+시리즈 AJAX POST (세션 저장)
                #   3) url(Basic2) GET (Referer=Basic1) → 해당 연도 정규시즌으로 열림
                #   4) url(Basic2)에서 팀 AJAX POST → 1페이지 데이터
                #   5) url(Basic2) 다시 GET (Referer=Basic2) → 팀 유지된 정상 HTML
                #      (페이지네이션에 필요한 정상 __VIEWSTATE 확보)

                # Step 1: Basic1 GET
                entry_html = self.fetch_page(entry_url)
                if not entry_html:
                    self.logger.warning(f"[{category}] {team_name} entry GET 실패, 건너뜀")
                    continue
                entry_result = self.parse_page(entry_html)

                # Step 2: Basic1에서 시리즈→정규시즌, 연도 설정
                if year is not None:
                    soup_ready = self._setup_year_on_page(
                        entry_url, entry_result["soup"], year
                    )
                    if not soup_ready:
                        self.logger.warning(f"[{category}] {team_name} 연도 설정 실패, 건너뜀")
                        continue

                # Step 3: Basic2 GET (Referer=Basic1으로 세션 상태 전달)
                html = self.fetch_page(url, referer=entry_url)
                if not html:
                    self.logger.warning(f"[{category}] {team_name} 데이터 페이지 GET 실패, 건너뜀")
                    continue
                fresh_result = self.parse_page(html)

                # Step 4: Basic2에서 팀 AJAX POST (1페이지 데이터)
                team_ajax_html = self._post_for_team(url, fresh_result["soup"], team_code)
                if not team_ajax_html:
                    self.logger.warning(f"[{category}] {team_name} 팀 필터 실패, 건너뜀")
                    continue

                # 1페이지 데이터 파싱 (AJAX 응답에서)
                team_result = self.parse_page(team_ajax_html)

                # Step 5: Basic2 다시 GET (팀 유지 + 정상 __VIEWSTATE 확보)
                # 페이지네이션 POST에는 정상 HTML의 __VIEWSTATE가 필요
                html = self.fetch_page(url, referer=url)
                if html:
                    fresh_for_paging = self.parse_page(html)
                    # 다시 GET한 soup을 페이지네이션용으로 사용
                    team_result["soup"] = fresh_for_paging["soup"]

            else:
                # 직접 접근 방식 (Basic1 등):
                #   1) url GET
                #   2) 시리즈→정규시즌, 연도 설정 (GET-POST 반복)
                #   3) url에서 팀 AJAX POST → 1페이지 데이터
                #   4) url 다시 GET (팀 유지 + 정상 __VIEWSTATE)

                html = self.fetch_page(url)
                if not html:
                    self.logger.warning(f"[{category}] {team_name} GET 실패, 건너뜀")
                    continue
                fresh_result = self.parse_page(html)

                if year is not None:
                    soup_ready = self._setup_year_on_page(url, fresh_result["soup"], year)
                    if not soup_ready:
                        self.logger.warning(f"[{category}] {team_name} 연도 설정 실패, 건너뜀")
                        continue
                    fresh_result = {"soup": soup_ready}

                # 팀 AJAX POST
                team_ajax_html = self._post_for_team(url, fresh_result["soup"], team_code)
                if not team_ajax_html:
                    self.logger.warning(f"[{category}] {team_name} 필터 실패, 건너뜀")
                    continue

                team_result = self.parse_page(team_ajax_html)

                # 다시 GET (팀 유지 + 페이지네이션용 정상 __VIEWSTATE)
                html = self.fetch_page(url, referer=url)
                if html:
                    fresh_for_paging = self.parse_page(html)
                    team_result["soup"] = fresh_for_paging["soup"]

            # 홈/원정 필터 적용 (경기상황별 드롭다운)
            if home_away:
                ha_value = "홈" if home_away == "홈" else "방문"
                # 경기상황별1: 홈/방문별
                self._post_for_situation(
                    url, team_result["soup"], HOME_AWAY_FILTER["situation_value"]
                )
                html = self.fetch_page(url, referer=url)
                if not html:
                    self.logger.warning(f"[{category}] {team_name} 홈/원정 필터1 실패, 건너뜀")
                    continue
                ha_result = self.parse_page(html)
                time.sleep(REQUEST_DELAY)

                # 경기상황별2: 홈(B) / 방문(T)
                detail_value = (
                    HOME_AWAY_FILTER["home_value"] if home_away == "홈"
                    else HOME_AWAY_FILTER["away_value"]
                )
                self._post_for_situation_detail(
                    url, ha_result["soup"], detail_value
                )
                html = self.fetch_page(url, referer=url)
                if not html:
                    self.logger.warning(f"[{category}] {team_name} 홈/원정 필터2 실패, 건너뜀")
                    continue
                team_result = self.parse_page(html)

            # 해당 팀의 모든 페이지 수집
            team_rows = self._scrape_all_pages(
                url, team_result["soup"], team_result, f"{category}/{team_name}"
            )

            # 첫 페이지 행도 포함
            if not team_rows:
                team_rows = team_result["rows"]

            # 중복 제거 (Player_ID 기준)
            for row in team_rows:
                pid = row[0] if row else ""
                if pid and pid in seen_player_ids:
                    continue
                if pid:
                    seen_player_ids.add(pid)
                all_rows.append(row)

            time.sleep(REQUEST_DELAY)

        self.logger.info(
            f"[{category}] 팀별 순회 완료 — 총 {len(all_rows)}명 수집"
        )
        return {"headers": all_headers, "rows": all_rows}

    def scrape_category_all(
        self, url: str, category: str, year: Optional[int] = None,
    ) -> dict:
        """
        팀 필터 없이 전체 순위 기반으로 수집 (기존 방식).
        규정타석 이상 선수만 포함될 수 있음.
        """
        self.logger.info(f"[{category}] 전체 순위 크롤링 시작 (연도: {year or '현재'})")

        html = self.fetch_page(url)
        if not html:
            return {"headers": [], "rows": []}

        result = self.parse_page(html)

        if year is not None:
            html = self._post_for_year(url, result["soup"], year)
            if not html:
                return {"headers": [], "rows": []}
            result = self.parse_page(html)

        all_rows = self._scrape_all_pages(url, result["soup"], result, category)
        if not all_rows:
            all_rows = result["rows"]

        self.logger.info(f"[{category}] 전체 순위 크롤링 완료 — {len(all_rows)}명")
        return {"headers": result["headers"], "rows": all_rows}

    # ============================================================
    # 팀 기록 크롤링 (파크팩터 계산용)
    # ============================================================

    def scrape_team_records(
        self, url: str, category: str, year: Optional[int] = None,
        home_away: Optional[str] = None,
    ) -> dict:
        """
        팀 기록 페이지를 크롤링한다.
        홈/원정 필터를 적용하여 파크팩터 계산에 필요한 데이터 수집.

        Args:
            url: 팀 기록 URL
            category: 카테고리명
            year: 시즌 연도
            home_away: "홈" | "방문" | None(전체)

        Returns:
            {"headers": [...], "rows": [[...], ...]}
        """
        self.logger.info(
            f"[{category}] 팀 기록 크롤링 (연도: {year or '현재'}, "
            f"홈/원정: {home_away or '전체'})"
        )

        html = self.fetch_page(url)
        if not html:
            return {"headers": [], "rows": []}

        result = self.parse_page(html)

        # 연도 변경 (시리즈→정규시즌 포함)
        if year is not None:
            soup_ready = self._setup_year_on_page(url, result["soup"], year)
            if not soup_ready:
                return {"headers": [], "rows": []}
            result = self.parse_page(
                self.fetch_page(url, referer=url) or ""
            )
            if not result.get("rows") and not result.get("headers"):
                return {"headers": [], "rows": []}

        # 홈/원정 필터 적용 (2단계 드롭다운)
        if home_away:
            # 1단계: 경기상황별1 → "홈/방문별" 선택
            self._post_for_situation(
                url, result["soup"], HOME_AWAY_FILTER["situation_value"]
            )
            # 다시 GET (경기상황별1 설정 반영)
            html = self.fetch_page(url, referer=url)
            if not html:
                self.logger.warning(f"  경기상황별1 필터 실패")
                return {"headers": [], "rows": []}
            result = self.parse_page(html)
            time.sleep(REQUEST_DELAY)

            # 2단계: 경기상황별2 → "홈"(B) 또는 "방문"(T) 선택
            detail_value = (
                HOME_AWAY_FILTER["home_value"] if home_away == "홈"
                else HOME_AWAY_FILTER["away_value"]
            )
            self._post_for_situation_detail(
                url, result["soup"], detail_value
            )
            # 다시 GET
            html = self.fetch_page(url, referer=url)
            if not html:
                self.logger.warning(f"  경기상황별2 필터 실패")
                return {"headers": [], "rows": []}
            result = self.parse_page(html)

            self.logger.info(f"  홈/원정 필터 적용 완료: {home_away}")

        return {"headers": result["headers"], "rows": result["rows"]}
