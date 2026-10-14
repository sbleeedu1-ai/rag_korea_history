"""기출처럼 풀기: 취재한 사건을 한국사능력검정시험처럼 5지선다로 확인하는 화면(2026-10-12 사용자 결정 [386]).

문제는 미리 써서 검수한 것만 쓴다(episode.QUIZ, AI가 즉석에서 만들지 않음). API를 부르지 않는다.
보기를 고르면 정답·해설과 근거 기사(우리 번역)를 보이고, 취재 수첩의 어느 갈래와 이어지는지 알려 준다.
모드 고르기 화면이 생기기 전까지는 사건 목록에 붙는 항목이다(app.EXTRA_PAGES 한 줄).
"""
from html import escape

import streamlit as st

from ui import episode as ep
from ui import view

NAME = "기출처럼 풀기"
SUBTITLE = f"{ep.TITLE} · 5지선다 {len(ep.QUIZ)}문제"
MARKS = "①②③④⑤"


def _state():
    return st.session_state.setdefault("quiz", {"i": 0, "picked": {}})


def _go(i):
    _state()["i"] = i


def _pick(qid, n):
    _state()["picked"].setdefault(qid, n)   # 처음 고른 답만 센다


def _restart():
    st.session_state.quiz = {"i": 0, "picked": {}}


def _dots(state):
    """문제 번호 줄: 지금 문제, 맞힘(✓), 틀림(✗)."""
    parts = []
    for i, q in enumerate(ep.QUIZ):
        picked = state["picked"].get(q["id"])
        mark = "" if picked is None else (" right" if picked == q["answer"] else " wrong")
        parts.append(f'<span class="qz-dot{mark}{" now" if i == state["i"] else ""}">{i + 1}</span>')
    return f'<div class="qz-dots">{"".join(parts)}</div>'


def _evidence(chunks, ids):
    by_id = {c["chunk_id"]: c for c in chunks}
    cards = [{"title": c["title_ko"], "record_date": c["record_date"], "speaker": c["speaker"], "translation": c["translation"],
              "original": c["original"], "chunk_id": c["chunk_id"]} for c in (by_id.get(i) for i in ids) if c]
    view.evidence_cards(cards, by_id)


def _question(chunks, state, q):
    picked = state["picked"].get(q["id"])
    st.html(f'<div class="qz-card"><div class="qz-label">{escape(q["label"])}</div>'
            f'<div class="qz-passage">{escape(q["passage"])}</div><div class="qz-ask">{escape(q["ask"])}</div></div>')
    if picked is None:
        with st.container(key="qz_options"):
            for n, text in enumerate(q["options"], 1):
                st.button(f"{MARKS[n - 1]}  {text}", key=f"qz_{q['id']}_{n}", use_container_width=True,
                          on_click=_pick, args=(q["id"], n))
        return
    rows = []
    for n, text in enumerate(q["options"], 1):
        cls = " right" if n == q["answer"] else (" wrong" if n == picked else "")
        tag = " · 정답" if n == q["answer"] else (" · 고른 답" if n == picked else "")
        rows.append(f'<div class="qz-opt{cls}">{MARKS[n - 1]}  {escape(text)}<span>{tag}</span></div>')
    verdict = "맞았습니다!" if picked == q["answer"] else f"아쉬워요. 정답은 {MARKS[q['answer'] - 1]}입니다."
    st.html(f'<div class="qz-opts">{"".join(rows)}</div>'
            f'<div class="qz-explain"><b>{verdict}</b><p>{escape(q["explain"])}</p>'
            f'<div class="qz-link">취재 수첩과 이어짐 · {escape(q["notebook"])}</div></div>')
    with st.expander("근거 기사 보기 · 우리 번역"):
        _evidence(chunks, q["sources"])


def _result(state):
    right = sum(state["picked"].get(q["id"]) == q["answer"] for q in ep.QUIZ)
    rows = "".join(f'<div class="qz-row{" right" if state["picked"].get(q["id"]) == q["answer"] else " wrong"}">'
                   f'<b>{i}. {escape(q["label"])}</b><span>{escape(q["notebook"])}</span></div>'
                   for i, q in enumerate(ep.QUIZ, 1))
    st.html(f'<div class="qz-card qz-result"><div class="qz-label">결과</div><h2>{len(ep.QUIZ)}문제 중 {right}문제를 맞혔어요</h2>'
            f'<p>틀린 문제는 취재 수첩의 해당 갈래를 다시 취재해 보세요.</p>{rows}</div>')
    a, b, _ = st.columns([1, 1, 2])
    a.button("다시 풀기", key="qz_again", use_container_width=True, on_click=_restart)
    b.button("취재하러 가기", key="qz_to_episode", use_container_width=True,
             on_click=lambda: st.session_state.update(pick_pending=ep.ID))   # 사건 카드를 고른 것과 같은 길(문제는 언문 논쟁)


def render(chunks, preview):
    state = _state()
    st.html(f'<div class="page-head"><span class="eyebrow">기출처럼 풀기 · {escape(ep.TITLE)}</span><h1>한국사능력검정시험처럼 풀어 보기</h1>'
            '<p>취재한 사건을 실록 사료로 확인합니다. 문제는 실록 원문과 우리 번역으로 새로 만들었으며 기출 문항을 옮긴 것이 아닙니다.</p></div>')
    st.html(_dots(state))
    if state["i"] >= len(ep.QUIZ):
        _result(state)
        return
    q = ep.QUIZ[state["i"]]
    _question(chunks, state, q)
    a, _, b = st.columns([1, 2, 1])
    if state["i"] > 0:
        a.button("← 이전 문제", key="qz_prev", use_container_width=True, on_click=_go, args=(state["i"] - 1,))
    last = state["i"] == len(ep.QUIZ) - 1
    b.button("결과 보기 →" if last else "다음 문제 →", key="qz_next", use_container_width=True, type="primary",
             disabled=q["id"] not in state["picked"], on_click=_go, args=(state["i"] + 1,))
