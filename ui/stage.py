"""취재 화면 전체를 그리는 Streamlit 커스텀 컴포넌트(CCv2, 2026-10-11 사용자 결정 [364]).

Streamlit 위젯을 CSS로 덮어 시안을 흉내 내던 방식([355]-[363])은 정렬·질감에 한계가 있어,
화면은 ui/stage_files/의 HTML·CSS·JS가 직접 그리고 Python은 데이터만 내려보낸다.
버튼을 누르면 JS가 trigger "action"으로 {type, ...}을 보내고, app.py가 엔진(runtime)으로 처리한다.
근거 보기·취재 의뢰·대화 기록·용어 도움말 창은 이미 받은 데이터로 브라우저 안에서 연다(추가 호출 없음).
"""
from pathlib import Path

import streamlit as st

FILES = Path(__file__).resolve().parent / "stage_files"


def _read(name: str) -> str:
    # 한 줄짜리 문자열은 파일 경로로 오해받으므로(CCv2 규칙) 내용 앞에 줄바꿈을 붙인다
    return "\n" + (FILES / name).read_text(encoding="utf-8")


def mount(data: dict, *, key: str, on_action, on_memo):
    """data: 화면에 그릴 모든 값. on_action: 버튼 행동이 오면 부를 콜백, on_memo: 내 메모가 바뀌면 부를 콜백."""
    # 등록은 실행 환경마다 필요해서(테스트처럼 실행 환경이 새로 생기면 모듈 import 때의 등록이 없어짐)
    # 마운트할 때 같은 내용으로 다시 등록한다. 실행 중인 서버는 처음 등록한 화면 파일을 계속 쓰므로,
    # stage_files를 고친 뒤에는 서버를 다시 켜야 반영된다.
    renderer = st.components.v2.component(
        "sillok_interview_stage", html=_read("stage.html"), css=_read("stage.css"), js=_read("stage.js"))
    # 창 높이를 꽉 채운다(바깥 상자 높이는 ui/style.css의 .st-key-stagewrap이 정함)
    return renderer(data=data, key=key, height="stretch", on_action_change=on_action, on_memo_change=on_memo)
