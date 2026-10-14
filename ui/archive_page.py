"""실록에 묻기: 사실 질문 화면(예시로 발표 시연 질문 3개).

처음에는 '시연용 함정 질문'으로 사건 목록에 붙었고([355]·[360]), 10-12 모드 고르기에서 정식 모드가 됐다([389]).
측정 때처럼 질문마다 새 대화로 답한다(runtime.create_session, 측정 D2 설정과 같음).
"""
from html import escape

import streamlit as st

from ui import runtime, view

NAME = "실록에 묻기"   # 10-12 모드 고르기에서 정식 모드로([389]). 측정한 사실 질문 설정 그대로
SUBTITLE = "실록 자료로 무엇이든 묻기 · 없는 건 지어내지 않음"


def _evidence(session, chunks):
    """답 바로 아래에 근거 기사를 펼친다(10-13 사용자: 팝업이 질문과 답을 가려 무엇을 하는지 안 보임)."""
    try:
        with st.spinner("답과 실록 구절을 대조하고 있습니다…"):
            evidence = runtime.request_evidence(session, 0)
    except Exception:
        st.error("근거를 불러오지 못했습니다. 답은 보존되어 있습니다. 다시 눌러 주세요.")
        return
    if evidence.get("error"):
        st.error("근거를 불러오지 못했습니다. 다시 눌러 주세요.")
        return
    st.html('<div class="speaker-tag">근거 기사</div>')
    view.evidence_cards(evidence.get("cards", []), {c["chunk_id"]: c for c in chunks})


def _toggle_evidence():
    st.session_state.archive_ev = not st.session_state.get("archive_ev")


def render(chunks, preview):
    # 한 번에 답 하나만 보인다(10-13 사용자: 대화 기록처럼 이어 붙이지 않음). 새 질문을 보내면 앞의 답과 근거는 닫힌다
    records = st.session_state.setdefault("archive", [])
    st.html('<div class="page-head"><span class="eyebrow">실록에 묻기</span><h1>실록에 직접 물어보세요</h1>'
            '<p>실록 자료에서 사실을 찾아 답합니다. 자료에 없는 내용은 지어내지 않고 확인되지 않는다고 답합니다. '
            '아래는 처음 보는 질문으로 시험한 예시입니다(잘 되는 질문 · 틀린 전제가 든 질문 · 자료에 없는 질문).</p></div>')
    prompt = None
    with st.container(key="archive_suggest"):
        for number, question in enumerate(runtime.FACT_QUESTIONS, 1):
            if st.button(f"{number}  {question}", key=f"archive_q{number}", use_container_width=True):
                prompt = question
    with st.form("archive_form", clear_on_submit=True, border=False):
        cols = st.columns([5, 1])
        text = cols[0].text_input("직접 질문하기", placeholder="궁금한 사실을 적어 주세요…",
                                  label_visibility="collapsed", key="archive_text")
        if cols[1].form_submit_button("질문하기", use_container_width=True) and text.strip():
            prompt = text.strip()
    if prompt:
        try:
            with st.spinner("실록 자료를 찾고 있습니다…"):
                session = runtime.create_session(chunks, None, preview=preview)
                runtime.ask_nonempty(session, prompt)
            records[:] = [session]
            st.session_state.archive_ev = False
        except Exception:
            # API 키 등이 담길 수 있는 예외 전문은 화면에 쓰지 않는다
            st.error("답을 가져오지 못했습니다. 다시 보내 주세요.")
    if not records:
        return
    session = records[-1]
    turn = session.log[0]
    with st.container(key="archive_item_0"):
        st.html(f'<div class="question-line">나의 질문 · {escape(turn.user)}</div>'
                '<div class="speaker-tag">기록 안내자</div>')
        if preview:
            by_id = {c["chunk_id"]: c for c in chunks}
            found = ", ".join(f"{by_id[c]['title_ko']}({by_id[c]['record_date'] or '총서'})" for c in turn.context_ids[:3] if c in by_id)
            st.html(f'<div class="answer-text muted">(미리보기) 실제 답변을 켜면 이 자리에 답이 나옵니다. '
                    f'찾은 자료: {escape(found or "없음")}</div>')
            return
        st.html(f'<div class="answer-text">{view.answer_html(turn.answer)}</div>')
        opened = st.session_state.get("archive_ev")
        st.button("근거 접기" if opened else "근거 보기", key="archive_ev_btn", on_click=_toggle_evidence)
        if opened:
            _evidence(session, chunks)
