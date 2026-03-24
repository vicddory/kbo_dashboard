"""
Streamlit 래퍼 — index.html 대시보드를 로컬 정적 서버 + iframe으로 임베드

실행:
  pip install -r requirements.txt
  streamlit run streamlit_app.py

※ 브라우저가 index.html·css·js·database/data.json 을 같은 오리진에서 불러와야 하므로
   127.0.0.1 임시 포트로 http.server 를 띄운 뒤 iframe 으로만 연결합니다.
   Streamlit Cloud 등 서버리스 배포에서는 백그라운드 소켓이 막힐 수 있어 로컬·자체 서버용입니다.
"""
from __future__ import annotations

import functools
import http.server
import os
import socketserver
import threading

import streamlit as st
import streamlit.components.v1 as components

# 프로젝트 루트 (index.html, css/, js/, database/ 위치)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _ensure_static_server() -> int:
    """세션당 1회만 127.0.0.1 에 정적 파일 서버 시작, 포트 반환"""
    if st.session_state.get("_static_port"):
        return int(st.session_state._static_port)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=BASE_DIR)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    st.session_state._httpd = httpd
    st.session_state._static_port = port
    return port


def main() -> None:
    st.set_page_config(
        page_title="KBO Stats+",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.sidebar.title("KBO Stats+")
    st.sidebar.markdown(
        "세이버메트릭스 대시보드(HTML)를 Streamlit 안에서 띄웁니다. "
        "차트·데이터는 기존 `database/data.json` 을 그대로 사용합니다."
    )
    port = _ensure_static_server()
    url = f"http://127.0.0.1:{port}/index.html"
    st.sidebar.markdown(f"[새 탭에서 열기]({url})")
    st.sidebar.caption(
        "Streamlit Cloud 등에서는 보조 프로세스·소켓이 제한될 수 있습니다. "
        "그때는 `python -m http.server` 로 정적 배포하거나 별도 웹서버에 올리세요."
    )

    st.markdown("### 대시보드")
    # iframe: 상대 경로 리소스가 동일 오리진에서 로드되도록 위 미니 서버 사용
    components.html(
        f'<iframe src="{url}" width="100%" height="920" style="border:none;border-radius:10px;overflow:hidden;" '
        f'title="KBO Stats+"></iframe>',
        height=940,
        scrolling=True,
    )


if __name__ == "__main__":
    main()
