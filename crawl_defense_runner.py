"""
수비/주루 기록 크롤러
- 팀 필터 없이 연도별 전체 선수 수집
- 연도 변경 전 btnFirst(첫 페이지)로 리셋
- 이미 DB에 있는 연도는 건너뜀
- 정규시즌만 (시리즈 선택 불필요)

사용법:
    python crawl_defense_runner.py
    python crawl_defense_runner.py --year-range 2001 2010
    python crawl_defense_runner.py --categories fielding_basic
    python crawl_defense_runner.py --categories runner_basic
"""

import sys
import time
import argparse
import logging
import sqlite3
from typing import Optional

from kbo_config import (
    KBO_OTHER_PAGES, ASPNET, CURRENT_YEAR,
    LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT, SQLITE_DB_PATH,
)
from kbo_crawler import KBOSeasonScraper
from data_parser import process_raw_data
from kbo_storage import SQLiteStorage
from bs4 import BeautifulSoup


def setup_logging():
    logging.basicConfig(
        level=LOG_LEVEL,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("kbo_scraper.log", encoding="utf-8"),
        ],
    )


def get_existing_years(db_path, category):
    """DB에서 이미 크롤링된 연도 목록 반환"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    conn.close()

    years = set()
    prefix = f"kbo_{category}_"
    for t in tables:
        if t.startswith(prefix):
            try:
                year_str = t[len(prefix):]
                year = int(year_str)
                years.add(year)
            except ValueError:
                continue
    return years


def parse_ajax_response(text):
    """AJAX 응답에서 HTML + hiddenField 추출하여 완전한 soup 반환"""
    html_content = ""
    hidden_fields = []

    # updatePanel HTML 추출
    marker = "|updatePanel|"
    idx = text.find(marker)
    if idx >= 0:
        pre = text[:idx]
        last_pipe = pre.rfind("|")
        length = int(pre[last_pipe + 1:])
        after = text[idx + len(marker):]
        pipe_pos = after.find("|")
        start = idx + len(marker) + pipe_pos + 1
        html_content = text[start:start + length]

    # hiddenField 추출
    pos = 0
    while True:
        hf_marker = "|hiddenField|"
        hf_idx = text.find(hf_marker, pos)
        if hf_idx < 0:
            break
        pre_hf = text[:hf_idx]
        last_pipe = pre_hf.rfind("|")
        try:
            value_length = int(pre_hf[last_pipe + 1:])
        except ValueError:
            pos = hf_idx + len(hf_marker)
            continue
        after_hf = text[hf_idx + len(hf_marker):]
        pipe1 = after_hf.find("|")
        if pipe1 < 0:
            break
        field_name = after_hf[:pipe1]
        value_start = hf_idx + len(hf_marker) + pipe1 + 1
        field_value = text[value_start:value_start + value_length]
        hidden_fields.append((field_name, field_value))
        pos = value_start + value_length

    if not html_content:
        return None, []

    # HTML + hiddenField 합쳐서 soup 생성
    hf_html = "\n".join(
        f'<input type="hidden" name="{n}" value="{v}" />'
        for n, v in hidden_fields
    )
    combined = f"<html><body>{html_content}\n{hf_html}</body></html>"
    soup = BeautifulSoup(combined, "html.parser")

    return soup, hidden_fields


def extract_table_data(soup):
    """soup에서 테이블 헤더와 행 데이터 추출"""
    headers = []
    rows = []

    tbl = soup.find("table")
    if not tbl:
        return headers, rows

    # 헤더
    thead = tbl.find("thead")
    if thead:
        ths = thead.find_all("th")
        headers = [th.text.strip() for th in ths]

    # 데이터 행
    tbody = tbl.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cells = [td.text.strip() for td in tr.find_all("td")]
            if cells:
                rows.append(cells)

    return headers, rows


def get_form_fields(soup):
    """soup에서 hidden fields + select 값 추출"""
    fields = {}
    for h in soup.find_all("input", {"type": "hidden"}):
        n = h.get("name", "")
        if n:
            fields[n] = h.get("value", "")
    for sel in soup.find_all("select"):
        n = sel.get("name", "")
        if not n:
            continue
        o = sel.find("option", selected=True)
        if o:
            fields[n] = o.get("value", "")
    return fields


def ajax_post(session, url, soup, event_target, extra_values=None):
    """AJAX POST 실행 후 원본 응답 텍스트 반환"""
    sm = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$smData"
    fields = get_form_fields(soup)
    fields["__EVENTTARGET"] = event_target
    fields["__EVENTARGUMENT"] = ""
    fields["__ASYNCPOST"] = "true"
    fields[sm] = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$udpContent|" + event_target
    if extra_values:
        fields.update(extra_values)

    resp = session.post(url, data=fields, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "X-MicrosoftAjax": "Delta=true",
        "Referer": url,
    }, timeout=15)
    return resp.text


def crawl_category_by_year(
    scraper: KBOSeasonScraper,
    sqlite: SQLiteStorage,
    url: str,
    category: str,
    year: int,
):
    """
    수비/주루 기록 크롤링 — AJAX 응답 직접 파싱 방식.
    re-GET하면 연도가 리셋되므로 AJAX 응답에서만 데이터를 추출.
    """
    logger = logging.getLogger("DefRunner")
    logger.info(f"[{category}] {year}년 수집 시작")

    session = scraper.session
    season_dd = ASPNET["season_dropdown"]
    pager_tpl = ASPNET["pager_btn_template"]

    # 1) 초기 GET (2026 빈 페이지)
    html = scraper.fetch_page(url)
    if not html:
        logger.warning(f"[{category}] {year}년 페이지 로드 실패")
        return False
    init_soup = BeautifulSoup(html, "html.parser")

    # 2) 연도 AJAX POST
    resp_text = ajax_post(session, url, init_soup, season_dd, {season_dd: str(year)})
    if "|pageRedirect|" in resp_text:
        logger.warning(f"[{category}] {year}년 연도 POST pageRedirect")
        return False

    ajax_soup, _ = parse_ajax_response(resp_text)
    if not ajax_soup:
        logger.warning(f"[{category}] {year}년 AJAX 파싱 실패")
        return False

    # 3) 첫 페이지 데이터 추출
    headers, all_rows = extract_table_data(ajax_soup)
    if not all_rows:
        logger.warning(f"[{category}] {year}년 데이터 없음")
        return False

    logger.info(f"[{category}] {year}년 1페이지: {len(all_rows)}행")

    # 4) 페이지네이션 (AJAX 응답 soup으로 계속 POST)
    current_soup = ajax_soup
    current_page = 1
    btn_next = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnNext"
    btn_first = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ucPager$btnFirst"

    while True:
        pager = current_soup.find("div", class_="paging")
        if not pager:
            break

        # 다음 페이지 번호 찾기: 페이저에서 현재 페이지+1의 text를 가진 버튼 찾기
        next_page = current_page + 1
        target_btn = None

        for a in pager.find_all("a"):
            txt = a.text.strip()
            if txt == str(next_page):
                # href에서 __doPostBack의 target 추출
                href = a.get("href", "")
                if "__doPostBack" in href:
                    # javascript:__doPostBack('ctl00$...$btnNo3','')
                    start = href.find("'") + 1
                    end = href.find("'", start)
                    target_btn = href[start:end]
                break

        if not target_btn:
            # 다음 페이지 번호가 현재 페이저에 없으면 > 버튼 시도
            next_exists = False
            for a in pager.find_all("a"):
                a_id = a.get("id", "")
                if "btnNext" in a_id:
                    next_exists = True
                    break

            if not next_exists:
                break  # > 버튼도 없으면 마지막

            # > 버튼 클릭 → 다음 그룹의 첫 페이지 데이터가 나옴
            logger.info(f"  [{category}/{year}] 다음 페이지 그룹으로 이동...")
            time.sleep(0.5)
            resp_text = ajax_post(session, url, current_soup, btn_next)
            if "|pageRedirect|" in resp_text or "|updatePanel|" not in resp_text:
                break
            next_soup, _ = parse_ajax_response(resp_text)
            if not next_soup:
                break
            _, next_rows = extract_table_data(next_soup)
            if not next_rows:
                break
            all_rows.extend(next_rows)
            current_page += 1
            current_soup = next_soup
            logger.info(f"  [{category}/{year}] {current_page}페이지: {len(next_rows)}행")
            continue

        # 번호 버튼 클릭
        logger.info(f"  [{category}/{year}] {next_page}페이지...")
        time.sleep(0.5)
        resp_text = ajax_post(session, url, current_soup, target_btn)
        if "|pageRedirect|" in resp_text or "|updatePanel|" not in resp_text:
            break
        page_soup, _ = parse_ajax_response(resp_text)
        if not page_soup:
            break
        _, page_rows = extract_table_data(page_soup)
        if not page_rows:
            break
        all_rows.extend(page_rows)
        current_page = next_page
        current_soup = page_soup

    logger.info(f"[{category}] {year}년 전체: {len(all_rows)}행")

    # 5) 첫 페이지로 리셋 (다음 연도 크롤링 전 준비)
    ajax_post(session, url, current_soup, btn_first)
    time.sleep(0.5)

    # 5) 정제 & 저장
    df = process_raw_data(
        headers=headers, rows=all_rows,
        category=category, year=year,
    )

    if df.empty:
        logger.warning(f"[{category}] {year}년 정제 후 데이터 없음")
        return False

    table = f"kbo_{category}_{year}"
    sqlite.save(df, table)
    logger.info(f"[{category}] {year}년 완료: {len(df)}행 → {table}")
    return True


def main():
    parser = argparse.ArgumentParser(description="KBO 수비/주루 기록 크롤러")
    parser.add_argument("--year-range", type=int, nargs=2, metavar=("START", "END"),
                        default=[1982, CURRENT_YEAR])
    parser.add_argument("--categories", nargs="+", default=["fielding_basic", "runner_basic"],
                        choices=["fielding_basic", "runner_basic"])
    parser.add_argument("--force", action="store_true",
                        help="이미 있는 연도도 다시 크롤링")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("DefRunner")

    start_year, end_year = args.year_range
    all_years = list(range(start_year, end_year + 1))

    sqlite = SQLiteStorage()
    scraper = KBOSeasonScraper()

    try:
        for category in args.categories:
            cat_info = KBO_OTHER_PAGES[category]
            url = cat_info["url"]

            # 이미 있는 연도 확인
            if args.force:
                skip_years = set()
            else:
                skip_years = get_existing_years(SQLITE_DB_PATH, category)

            todo_years = [y for y in all_years if y not in skip_years]
            skipped = [y for y in all_years if y in skip_years]

            logger.info(f"{'='*50}")
            logger.info(f"{category} — {cat_info['description']}")
            logger.info(f"전체: {len(all_years)}개 연도 ({start_year}~{end_year})")
            logger.info(f"건너뜀: {len(skipped)}개 (이미 DB에 있음)")
            logger.info(f"크롤링: {len(todo_years)}개")
            if skipped:
                logger.info(f"  건너뛴 연도: {skipped}")
            logger.info(f"{'='*50}")

            if not todo_years:
                logger.info(f"[{category}] 모든 연도 이미 수집됨!")
                continue

            success = 0
            fail = 0

            for year in todo_years:
                try:
                    ok = crawl_category_by_year(scraper, sqlite, url, category, year)
                    if ok:
                        success += 1
                    else:
                        fail += 1
                except Exception as e:
                    logger.error(f"[{category}] {year}년 에러: {e}")
                    fail += 1

                time.sleep(1.0)

            logger.info(f"\n[{category}] 결과: 성공 {success}, 실패 {fail}")

    except KeyboardInterrupt:
        logger.info("사용자 중단")
    finally:
        scraper.close()
        sqlite.close()


if __name__ == "__main__":
    main()