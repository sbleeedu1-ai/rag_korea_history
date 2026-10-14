"""화면 조각: 답 본문의 용어 표시, 오른쪽 용어 도움말 창, 답 성격 태그, 근거 기사 카드.

용어 도움말 창은 Python 재실행 없이 CSS만으로 열고 닫는다(라디오 입력 + :has). 답 속 밑줄 단어나
위쪽 '용어 도움말' 버튼을 누르면 오른쪽에서 창이 열린다(2026-10-11 사용자 제안).
"""
import re
from html import escape

import streamlit as st

from ui.episode import INLINE_TERMS, TERMS

# 출처 표시(공공누리 제1유형의 조건). 취재 화면의 근거 기사 창(stage_files/stage.js)에도 같은 문장이 있다
SOURCE_NOTICE = "원문 출처: 국사편찬위원회 「조선왕조실록」(공공누리 제1유형)"
CREDIT_NOTICE = (f"{SOURCE_NOTICE} · 번역·풀이는 이 프로젝트가 한문 원문에서 직접 한 것(국역본 아님) · "
                 "인물·배경 그림은 GPT Image로 만든 창작 그림")
from sillok_rag.corpus import sillok_url

TERM_IDS = {term: f"gl-t-{i}" for i, term in enumerate(TERMS)}


_ID = r"w[a-z]{2}_\d{8}_\d{3}-\d{2}"
_ID_LIST = rf"{_ID}(?:\s*[,·、]\s*{_ID})*"
# 답변 모델이 붙이는 머리말은 "근거"·"출처"·"기사 ID"·"관련 기록" 등으로 바뀐다(10-12 리허설에서 "(기사 ID: )"만 남음)
_LABEL = r"(?:근거|출처|참고|관련\s*기록|기사\s*ID|ID)"
_SOURCE_NOTES = [re.compile(p) for p in (
    rf"(?m)^[ \t]*[-*·]?[ \t]*\(?{_LABEL}[^\n]*{_ID}[^\n]*$",            # '근거: …'로 시작하는 줄은 통째로
    rf"[(\[]\s*(?:{_LABEL}[^)\]\n]{{0,12}}?[:：]\s*)?{_ID_LIST}\s*[)\]]",   # (근거: wda_…) · (기사 ID: wda_…) · [wda_…]
    rf"{_LABEL}[^\n:：]{{0,12}}[:：]\s*{_ID_LIST}\.?",                     # 근거: wda_…, wda_…
    _ID,                                                                  # 남은 ID
    rf"[(\[]\s*{_LABEL}[^)\]\n]{{0,12}}?[:：]?\s*[)\]]",                  # ID만 빠지고 남은 빈 괄호 "(기사 ID: )"
)]


def strip_source_ids(text: str) -> str:
    """화면에 보일 답에서 기사 ID 표기(근거: wda_…)를 뺀다. 근거는 '근거 보기'가 기사 제목으로 보여 준다(사용자 10-12).
    답변 규칙(sillok_rag)은 그대로 ID를 적게 두고, 대화 원본(session.log)도 바꾸지 않는다."""
    for pattern in _SOURCE_NOTES:
        text = pattern.sub("", text or "")
    return re.sub(r"[ \t]+\n|\n{3,}", "\n", re.sub(r"[ \t]{2,}", " ", text)).strip()


def answer_html(text: str) -> str:
    """모델 답을 이스케이프한 뒤, 용어의 첫 등장만 도움말 창을 여는 밑줄 단어로 바꾼다."""
    body = escape(re.sub(r"\*\*(.+?)\*\*", r"\1", strip_source_ids(text)).strip())
    for term in sorted(INLINE_TERMS, key=len, reverse=True):
        pos = body.find(term)
        # 이미 바꾼 표시 안(라벨 속)은 건드리지 않는다
        if pos < 0 or body.rfind("<label", 0, pos) > body.rfind("</label>", 0, pos):
            continue
        body = (body[:pos] + f'<label class="term" for="{TERM_IDS[term]}">{term}</label>'
                + body[pos + len(term):])
    return body.replace("\n", "<br>")


_SENTENCE_END = re.compile(r"(?<=[.?!。…])\s+|\n+")


def sentences_html(text: str, terms=None) -> list[str]:
    """취재 화면 대화창용: 답을 문장으로 나눠(쪽 나누기 단위) 이스케이프하고, 용어의 첫 등장에 표시를 붙인다.
    표시는 누르면 오른쪽 용어 도움말 창이 열리는 span(data-term)이다. terms: 지금 사건의 용어(없으면 언문 논쟁)."""
    plain = re.sub(r"\*\*(.+?)\*\*", r"\1", strip_source_ids(text)).strip()
    seen, out = set(), []
    for sentence in (s.strip() for s in _SENTENCE_END.split(plain)):
        if not sentence:
            continue
        body = escape(sentence)
        for term in sorted(terms or INLINE_TERMS, key=len, reverse=True):
            pos = body.find(term)
            if term in seen or pos < 0 or body.rfind("<span", 0, pos) > body.rfind("</span>", 0, pos):
                continue
            seen.add(term)
            body = body[:pos] + f'<span class="term" data-term="{term}" tabindex="0">{term}</span>' + body[pos + len(term):]
        out.append(body)
    return out or [""]


def highlight_html(translation: str, quotes: list[str]) -> str:
    """근거 기사 번역문을 이스케이프하고, 답이 기댄 구절에 형광펜 표시를 한다."""
    return _highlight(translation, quotes)


def terms_in(text: str) -> list[str]:
    return [t for t in INLINE_TERMS if t in (text or "")]


def glossary_drawer() -> None:
    """오른쪽 용어 도움말 창. 한 화면에 한 번만 그린다."""
    radios = ['<input type="radio" name="gl" id="gl-close" class="gl-radio" checked>',
              '<input type="radio" name="gl" id="gl-all" class="gl-radio">']
    radios += [f'<input type="radio" name="gl" id="{rid}" class="gl-radio">' for rid in TERM_IDS.values()]
    items = "".join(f'<div class="gl-item" id="i-{TERM_IDS[t]}"><b>{escape(t)}</b><p>{escape(d)}</p></div>'
                    for t, d in TERMS.items())
    focus = "".join(f"body:has(#{rid}:checked) #i-{rid}{{background:#efe2bf;border-color:#b08d4f}}"
                    for rid in TERM_IDS.values())
    st.html(f'<style>{focus}</style>{"".join(radios)}<aside class="glossary" aria-label="용어 도움말">'
            '<div class="gl-head"><span>용어 도움말</span><label for="gl-close" class="gl-close" title="닫기">✕</label></div>'
            '<p class="gl-note">답에 밑줄 친 말을 누르면 여기서 뜻을 볼 수 있어요. 이번 자료를 읽는 데 필요한 범위의 짧은 풀이입니다.</p>'
            f'{items}</aside>')


def answer_tag(evidence) -> str:
    """답 전체의 성격을 작은 태그 하나로(문장별 판정은 보이지 않는다)."""
    segments = (evidence or {}).get("segments") or []
    if any(s.get("label") == "기록" and s.get("verified") for s in segments):
        return "실록 기록 바탕"
    if any(s.get("label") == "해석" for s in segments):
        return "실록 기반 풀이"
    return "기록 기반 재구성"


def _highlight(translation: str, quotes: list[str]) -> str:
    body = escape(translation)
    for quote in quotes:
        q = escape(quote)
        if q and q in body:
            body = body.replace(q, f"<mark>{q}</mark>", 1)
    return body


def sillok_source(chunk: dict) -> str:
    """어느 실록의 어느 날 기사인지: '세종실록 · 세종 14년 6월 9일'. 연산군·광해군은 '일기', 선조 수정실록은 따로 부른다."""
    king = chunk.get("king") or ""
    if king.endswith("(수정실록)"):
        book, king = king.replace("(수정실록)", "") + "수정실록", king.replace("(수정실록)", "")
    else:
        book = king + ("일기" if king in ("연산군", "광해군") else "실록")
    reign = (chunk.get("reign") or "").replace("(수정실록)", "")
    date = chunk.get("record_date")
    if not date:
        return f"{book} · {reign}"
    _, month, day = date.split("-")
    return f"{book} · {reign} {'윤' if chunk.get('leap_month') else ''}{int(month)}월 {int(day)}일"


def evidence_cards(cards: list[dict], by_id: dict | None = None) -> None:
    """근거 기사 카드: 어느 실록의 어느 날 기사인지·제목·화자, 우리 번역(답이 기댄 구절 강조), 한문 원문, 원문 링크."""
    if not cards:
        st.info("이 답에는 실록 기록과 직접 이어진 문장이 없습니다. 기록을 풀어 쓴 설명이나 재구성한 말일 수 있어요.")
        return
    for card in cards:
        chunk = (by_id or {}).get(card["chunk_id"])
        when = (f'{sillok_source(chunk)} ({chunk.get("record_date") or "총서"})' if chunk
                else card.get("record_date") or "날짜 없는 총서")
        st.html(f'<div class="ev-card"><div class="ev-source">{escape(when)}</div><div class="ev-title">{escape(card["title"])}</div>'
                f'<div class="ev-meta">화자 {escape(card["speaker"])}</div>'
                f'<div class="ev-label">우리 번역 · 한문 원문에서 직접 번역한 AI 초안, 일부 사람 검수</div>'
                f'<div class="ev-text">{_highlight(card["translation"], card.get("quotes", []))}</div></div>')
        with st.expander("한문 원문 보기"):
            st.write(card["original"])
        st.link_button("국사편찬위원회 실록 원문 ↗", card.get("url") or sillok_url(card["chunk_id"].split("-")[0]))
        st.caption(SOURCE_NOTICE)
