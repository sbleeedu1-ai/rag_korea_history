"""시험 모드(서버를 켤 때 SILLOK_FAST=1): 측정 뒤 시험한 두 가지를 시연 화면에서만 켠다. 기본은 꺼짐(측정 설정 그대로).

- 리랭커 생각 수준 low → none(작업기록 [414]-[415]: 개발 단발 115·대화 50에서 정답 수·검색 적중이 같고 문항당 25-35% 빠름)
- 근거 대조를 '중간 방식'으로([416]): 코드가 답을 번호 붙인 문장으로 나누고, 모델은 번호·표시·근거 ID·구절만 낸다.
  답 문장을 다시 옮겨 쓰지 않아 출력이 짧다(대화 50턴 중앙값 9.2 → 7.5초, 목표 항목 17 → 17).
- 근거 대조의 생각 수준 medium → low([418]: 같은 20턴 중앙값 9.2 → 5.1초·최대 19.9 → 8.9초, 잘못 붙인 기록 0.
  none은 2.8초였으나 마무리 말에 엉뚱한 구절을 붙인 것이 1개 있어 low로)
엔진(sillok_rag/)은 바꾸지 않는다. 결과 형식은 evidence.annotate와 같아 화면·목표 도장 코드는 그대로 쓴다.
"""
import json
import os
import re

from sillok_rag.evidence import EVIDENCE_RULES, _squash, cards, evidence_messages, verify

ON = os.environ.get("SILLOK_FAST", "").strip() == "1"
RERANK_EFFORT = "none"
EVIDENCE_EFFORT = "low"
LABEL = "시험 설정(측정과 다름): 리랭커 생각 끔 · 근거 대조는 문장 번호로·생각 low · 답변 medium · 자료 6개"
_evidence_llm = None

RULES = EVIDENCE_RULES.split("- text에는")[0].replace(
    "[답변]을 문장(또는 뜻이 나뉘는 구절) 단위로 나누고, 각 부분에 표시 하나를 붙이세요.",
    "[답변]은 번호를 붙인 문장으로 나뉘어 있습니다. 각 번호에 표시 하나를 붙이세요.") + \
    '- 답변 글을 다시 쓰지 말고 번호만 쓰세요.\n' \
    '- JSON으로만 답하세요: {"labels": [{"n": 1, "label": "기록|해석|시점|창작", "source": "ID|카드|앞선 답|", "quote": "…"}]}'

_SENT = re.compile(r"[^.?!。\n]+[.?!。]?[」”’\"')]*")


def sentences(answer: str) -> list[str]:
    """답을 문장으로 나눈다(마침표·물음표·느낌표·줄바꿈 기준). 나눈 문장은 모두 답의 글자 그대로다."""
    return [s.strip() for s in _SENT.findall(answer or "") if len(_squash(s)) >= 2]


def annotate(llm, answer: str, chunks: list[dict], known_facts=None, prior_answers=None, lookup=None) -> dict:
    """evidence.annotate와 같은 결과를 낸다. 모델 답을 못 쓰면 표시 없이(버튼 없음) 돌려준다."""
    sents = sentences(answer)
    msgs = evidence_messages(answer, chunks, known_facts, prior_answers)
    msgs[0]["content"] = RULES
    msgs[1]["content"] = msgs[1]["content"].rsplit("[답변]", 1)[0] + "[답변]\n" + "\n".join(
        f"{i}. {s}" for i, s in enumerate(sents, 1))
    try:
        raw = json.loads(llm.chat(msgs, json_mode=True)).get("labels") or []
        error = None
    except Exception as e:  # 키가 담길 수 있어 예외 종류만 남긴다
        raw, error = [], type(e).__name__
    segs = []
    for item in raw if isinstance(raw, list) else []:
        try:
            text = sents[int(item.get("n")) - 1]
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
        segs.append({"text": text, "label": item.get("label"), "source": item.get("source"), "quote": item.get("quote")})
    segments = verify(segs, answer, chunks, known_facts, prior_answers)
    found = cards(segments, chunks, known_facts, lookup)
    return {"segments": segments, "cards": found, "show_button": bool(found), "error": error,
            "raw": raw if isinstance(raw, list) else []}


def evidence_for(session, index: int) -> dict:
    """ChatSession.evidence_for와 같은 자료(고른 청크·인물 카드·앞선 답)로 annotate를 부른다."""
    t = session.log[index]
    by_id = {c["chunk_id"]: c for c in session.chunks}
    ctx = [by_id[cid] for cid in t.context_ids if cid in by_id]
    is_char = t.speaker == "character"
    prior = [x.answer for x in session.log[:index] if x.speaker == "character"] if is_char else None
    t.evidence = annotate(evidence_llm(session.llm), t.answer, ctx, session.known_facts if is_char else None, prior, by_id)
    return t.evidence


def evidence_llm(answer_llm):
    """근거 대조용 모델: 답변 모델과 같은 모델·키, 생각 수준만 low. 미리보기(dry_run)면 답변 모델을 그대로 쓴다."""
    global _evidence_llm
    if answer_llm.dry_run:
        return answer_llm
    if _evidence_llm is None:
        from ui.runtime import api_key
        from sillok_rag.llm import LLM

        _evidence_llm = LLM(model=answer_llm.model, api_key=api_key(), reasoning_effort=EVIDENCE_EFFORT)
    return _evidence_llm
