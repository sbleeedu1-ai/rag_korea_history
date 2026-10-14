"""근거 보기: 답변 문장마다 실록 기록 / 실록 풀이 / 인물 시점 / AI 창작을 붙이고, 실록 기록 문장에는 근거 기사 카드를 단다.

화면의 [근거 보기] 버튼을 눌렀을 때 보여 줄 내용을 만든다(작업기록 [196], 화면 기획 [185]).
- 답변을 만든 뒤 별도 호출 한 번으로 표시를 붙인다. 답변 자체(말투·내용)는 건드리지 않는다.
- 실록 기록은 근거 구절이 그 청크 번역문(또는 아는 사실 카드)에 **글자 그대로 있을 때만** 인정한다.
  확인이 안 되면 기록 표시와 카드를 떼고 실록 풀이(해석)로 둔다. 화면에 없는 출처를 보여 주지 않기 위한 안전장치다.
  인물의 앞선 답은 실록이 아니므로 기록 근거가 될 수 없다([204]: "아직 알지 못하오"가 실록 기록으로 보이던 문제).
- 내부 표시 이름(기록·해석·시점·창작)과 화면 이름(실록 기록·실록 풀이·인물 시점·AI 창작)은 다르다([205] 사용자 결정).
- 인물 시점은 "이 시점에는 아직 모른다"는 말과, 모르는 앞일을 가정하는 말이다([207] 사용자 검수). 근거도 카드도 없다.
- 창작은 말투·인사·감정·장면 연출에만 쓴다. 날짜·인물·사건 같은 사실이나 "그렇지 않소" 같은 사실 판단을 창작으로 붙이지 않는다.
- 틀린 답(예: 상소에 28자라고 썼다)은 표시로 처리하지 않는다. 그런 답은 답변 품질과 채점에서 다룬다.
- 버튼은 실록 기록 문장이 하나라도 있을 때만 보인다(인사·연출뿐인 답에는 근거 보기가 없다).
"""
import json
import re

from .corpus import cite, sillok_url

LABELS = ("기록", "해석", "시점", "창작")

EVIDENCE_RULES = """당신은 역사 인물 인터뷰 답변에 근거 표시를 붙이는 도우미입니다. [답변]을 문장(또는 뜻이 나뉘는 구절) 단위로 나누고, 각 부분에 표시 하나를 붙이세요.
- 기록: [자료]·[아는 사실]에 적힌 사실이나 발언을 그대로 또는 바꿔 말한 부분. source에 근거 ID([자료]의 ID 또는 "카드")를, quote에 그 근거에서 **글자 그대로 옮긴 구절**(8-60자, 괄호 속 한자는 빼도 됨)을 쓰세요. [앞선 답]은 실록이 아니므로 기록의 근거로 쓰지 마세요.
- 해석: [자료]·[아는 사실]에 기대지만 직접 적히지 않은 요약·추론·의미 부여. 질문의 전제가 맞다/틀리다는 판단("그렇지 않소", "그렇소")도 해석입니다. source에 기댄 근거 ID를 쓰고 quote는 비워 두세요.
- 시점: 인물이 이 시점에는 아직 모르거나 알 수 없다는 말("그 뒤의 일은 알지 못하오", "단정할 수 없소"), 그리고 모르는 앞일을 가정하는 말("그 일이 참으로 일어난다면"). source와 quote는 비워 두세요.
- 창작: 말투, 인사, 감정 표현, 장면 묘사처럼 인터뷰를 위한 연출. source와 quote는 비워 두세요. 날짜·인물·사건·수 같은 사실과 사실 판단은 창작으로 표시하지 마세요.
- text에는 [답변]의 글자를 그대로 옮기세요. 답변을 고치거나 덧붙이지 마세요.
- JSON으로만 답하세요: {"segments": [{"text": "…", "label": "기록|해석|시점|창작", "source": "ID|카드|앞선 답|", "quote": "…"}]}"""


def evidence_messages(answer: str, chunks: list[dict], known_facts: list[dict] | None = None,
                      prior_answers: list[str] | None = None) -> list[dict]:
    parts = [f"ID: {c['chunk_id']} · {c['title_ko']} · 화자 {c['speaker']} · 기록일 {c['record_date'] or '총서'}\n"
             f"{c['translation']}" for c in chunks]
    user = "[자료]\n" + "\n\n".join(parts)
    if known_facts:
        user += "\n\n[아는 사실]\n" + "\n".join(f"- {f['fact']}" for f in known_facts)
    if prior_answers:
        user += "\n\n[앞선 답]\n" + "\n".join(f"- {a}" for a in prior_answers)
    user += f"\n\n[답변]\n{answer}"
    return [{"role": "system", "content": EVIDENCE_RULES}, {"role": "user", "content": user}]


_HAN_PAREN = re.compile(r"\([^()]*[㐀-䶿一-鿿豈-﫿][^()]*\)")


def _squash(text) -> str:
    """대조용으로 고른다: 괄호 속 한자 병기(예: 최만리(崔萬理))와 공백·문장부호를 뺀다.
    번역문은 한자를 병기하는데 모델은 빼고 옮겨, 글자 그대로 비교하면 맞는 근거도 떨어졌다([196] 1차)."""
    text = _HAN_PAREN.sub("", text if isinstance(text, str) else "")
    return re.sub(r"[\s\W_]+", "", text)


def verify(segments, answer: str, chunks: list[dict], known_facts: list[dict] | None = None,
           prior_answers: list[str] | None = None) -> list[dict]:
    """모델이 준 표시를 코드로 확인한다.
    - text가 답변에 없으면 버린다(답변을 바꿔 옮긴 것).
    - 기록은 source가 실록 근거([자료] 청크나 카드)이고 quote(5자 이상)가 그 근거 글에 글자 그대로 있을 때만 남긴다.
      아니면 해석으로 내린다. 앞선 답을 근거로 단 기록도 해석으로 내린다(실록이 아님, [204]).
    - 해석의 source가 [자료]·카드·앞선 답이 아니면 지운다. 시점·창작은 source·quote를 비운다.
    """
    by_id = {c["chunk_id"]: c for c in chunks}
    texts = {"카드": _squash(" ".join(f["fact"] for f in known_facts or [])),
             "앞선 답": _squash(" ".join(prior_answers or []))}
    flat = _squash(answer)
    out = []
    for seg in segments if isinstance(segments, list) else []:
        if not isinstance(seg, dict):
            continue
        text, label = str(seg.get("text") or "").strip(), seg.get("label")
        if not text or _squash(text) not in flat or label not in LABELS:
            continue
        source, quote = str(seg.get("source") or "").strip(), str(seg.get("quote") or "").strip()
        verified = False
        if label == "기록":
            base = _squash(by_id[source]["translation"]) if source in by_id else (texts["카드"] if source == "카드" else "")
            verified = len(_squash(quote)) >= 5 and _squash(quote) in base
            if not verified:
                label, quote = "해석", ""
        if label == "해석":
            quote = ""
            if source not in by_id and source not in texts:
                source = ""
        if label in ("시점", "창작"):
            source, quote = "", ""
        out.append({"text": text, "label": label, "source": source, "quote": quote,
                    "verified": verified})
    return out


def cards(segments: list[dict], chunks: list[dict], known_facts: list[dict] | None = None,
          lookup: dict | None = None) -> list[dict]:
    """실록 기록(확인된 것)이 가리키는 기사 카드. 같은 청크는 하나로 묶고 강조 구절을 모은다.
    아는 사실 카드에서 온 기록은 그 카드의 근거 청크(lookup에서 찾음)로 카드를 단다. 인물의 앞선 답에서 온 기록은 카드가 없다."""
    by_id = {c["chunk_id"]: c for c in chunks}
    out: dict[str, dict] = {}
    for s in segments:
        if s["label"] != "기록" or not s["verified"]:
            continue
        cid = s["source"]
        if cid == "카드":
            fact = next((f for f in known_facts or [] if _squash(s["quote"]) in _squash(f["fact"])), None)
            cid = fact.get("source") if fact else None
        c = by_id.get(cid) or (lookup or {}).get(cid)
        if c is None:
            continue
        card = out.setdefault(c["chunk_id"], {
            "chunk_id": c["chunk_id"], "title": c["title_ko"], "record_date": c["record_date"],
            "source": c.get("source", ""), "cite": cite(c), "url": sillok_url(c["article_id"]),
            "speaker": c["speaker"], "original": c["original"], "translation": c["translation"], "quotes": []})
        if s["quote"] not in card["quotes"]:
            card["quotes"].append(s["quote"])
    return list(out.values())


def annotate(llm, answer: str, chunks: list[dict], known_facts: list[dict] | None = None,
             prior_answers: list[str] | None = None, lookup: dict | None = None) -> dict:
    """답변 하나에 근거 보기 내용을 만든다. 모델 답을 못 쓰면 표시 없이(버튼 없음) 돌려준다."""
    try:
        reply = json.loads(llm.chat(evidence_messages(answer, chunks, known_facts, prior_answers), json_mode=True))
        raw = reply.get("segments")
        error = None
    except Exception as e:  # 키가 담길 수 있어 예외 종류만 남긴다
        raw, error = [], type(e).__name__
    segments = verify(raw, answer, chunks, known_facts, prior_answers)
    found = cards(segments, chunks, known_facts, lookup)
    return {"segments": segments, "cards": found, "show_button": bool(found), "error": error,
            "raw": raw if isinstance(raw, list) else []}   # 모델이 준 그대로(확인 전). 표시가 떨어진 까닭을 볼 때 씀
