"""근거 대조 빠른 방식 시험(유료). 저장소 코드는 바꾸지 않는다.

지금 방식: 모델이 답 문장을 다시 옮겨 쓰고 표시·근거 ID·원문 구절(quote)까지 JSON으로 낸다.
빠른 방식: 코드가 답을 문장으로 나눠 번호를 붙이고, 모델은 번호·표시·근거 ID만 낸다.
          '기록'의 원문 구절은 코드가 그 근거 글에서 답 문장과 가장 많이 겹치는 마디를 골라 채운다.
두 방식 모두 결과는 evidence.verify()·cards()를 그대로 거친다(화면이 받는 형식이 같음).
대상: results/20261013_리랭커none 대화 A-E의 답(답변 호출은 다시 하지 않음).
"""
import glob
import json
import re
import sys
import time

sys.path.insert(0, r"C:\sample\rag_korea_history_test")
from sillok_rag.corpus import load_chunks
from sillok_rag.evaluate import load_all_scenarios
from sillok_rag.evidence import EVIDENCE_RULES, _squash, annotate, cards, evidence_messages, verify
from sillok_rag.llm import LLM

FAST_RULES = EVIDENCE_RULES.split("- text에는")[0].replace(
    "[답변]을 문장(또는 뜻이 나뉘는 구절) 단위로 나누고, 각 부분에 표시 하나를 붙이세요.",
    "[답변]은 번호를 붙인 문장으로 나뉘어 있습니다. 각 번호에 표시 하나를 붙이세요.").replace(
    "를, quote에 그 근거에서 **글자 그대로 옮긴 구절**(8-60자, 괄호 속 한자는 빼도 됨)을 쓰세요. ", "를 쓰세요. ").replace(
    "source에 기댄 근거 ID를 쓰고 quote는 비워 두세요.", "source에 기댄 근거 ID를 쓰세요.").replace(
    "source와 quote는 비워 두세요.", "source는 비워 두세요.") + \
    '- 답변 글을 다시 쓰지 말고 번호만 쓰세요.\n- JSON으로만 답하세요: {"labels": [{"n": 1, "label": "기록|해석|시점|창작", "source": "ID|카드|앞선 답|"}]}'

_SENT = re.compile(r"[^.?!。\n]+[.?!。]?[」”’\"')]*")
_CLAUSE = re.compile(r"[^.,;:?!。、“”\"'「」『』\n]+")


def sentences(answer):
    return [s.strip() for s in _SENT.findall(answer) if len(_squash(s)) >= 2]


def bigrams(text):
    t = _squash(text)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def best_quote(sentence, base_text):
    """근거 글을 띄어쓰기 단위로 이은 창(한자 괄호·부호를 뺀 길이 8-60자) 가운데 답 문장과 2글자 묶음이
    가장 많이 겹치는 것. 점수 = 겹친 수 × 창 쪽 비율. 겹친 수 6개 이상·비율 0.5 이상일 때만 구절로 쓴다."""
    sb = bigrams(sentence)
    spans = [m.span() for m in re.finditer(r"\S+", base_text)]
    best, key = ("", 0, 0.0), 0.0
    for i in range(len(spans)):
        for j in range(i, len(spans)):
            win = base_text[spans[i][0]:spans[j][1]].strip("“”\"'「」『』(),.")
            n = len(_squash(win))
            if n > 60:
                break
            if n < 8:
                continue
            cb = bigrams(win)
            shared = len(cb & sb)
            ratio = shared / max(len(cb), 1)
            if shared * ratio > key:
                best, key = (win, shared, ratio), shared * ratio
    win, shared, ratio = best
    return (win, ratio) if shared >= 6 and ratio >= 0.5 else ("", ratio)


def annotate_fast(llm, answer, chunks, known_facts=None, prior_answers=None, lookup=None):
    sents = sentences(answer)
    msgs = evidence_messages(answer, chunks, known_facts, prior_answers)
    msgs[0]["content"] = FAST_RULES
    msgs[1]["content"] = msgs[1]["content"].rsplit("[답변]", 1)[0] + "[답변]\n" + "\n".join(
        f"{i}. {s}" for i, s in enumerate(sents, 1))
    try:
        raw = json.loads(llm.chat(msgs, json_mode=True)).get("labels") or []
        error = None
    except Exception as e:
        raw, error = [], type(e).__name__
    by_id = {c["chunk_id"]: c for c in chunks}
    card_text = " ".join(f["fact"] for f in known_facts or [])
    segs = []
    for item in raw if isinstance(raw, list) else []:
        try:
            text = sents[int(item.get("n")) - 1]
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
        label, source = item.get("label"), str(item.get("source") or "").strip()
        quote = ""
        if label == "기록":
            base = by_id[source]["translation"] if source in by_id else (card_text if source == "카드" else "")
            quote, _ = best_quote(text, base)
        segs.append({"text": text, "label": label, "source": source, "quote": quote})
    segments = verify(segs, answer, chunks, known_facts, prior_answers)
    return {"segments": segments, "cards": cards(segments, chunks, known_facts, lookup),
            "show_button": bool(cards(segments, chunks, known_facts, lookup)), "error": error}


def timed(llm, fn, *a, **k):
    before = dict(llm.usage)
    t = time.perf_counter()
    out = fn(llm, *a, **k)
    return out, time.perf_counter() - t, llm.usage["completion"] - before["completion"], \
        llm.usage["reasoning"] - before["reasoning"]


def main(out_path):
    chunks = load_chunks()
    by_id = {c["chunk_id"]: c for c in chunks}
    scs = load_all_scenarios()
    llm = LLM()   # 지금 근거 대조와 같은 설정(답변 모델·medium)
    rows_out = []
    for sid in "ABCDE":
        f = sorted(glob.glob(rf"C:\sample\rag_korea_history_test\results\20261013_리랭커none\*scenario{sid}_*.jsonl"))[-1]
        rows = [json.loads(l) for l in open(f, encoding="utf-8")]
        prior = []
        for r in rows:
            is_char = r["speaker"] == "character"
            if r["qid"].endswith("0") and len(r["qid"]) == 2:
                if is_char:
                    prior.append(r["answer"])
                continue
            ctx = [by_id[c] for c in r["context_ids"] if c in by_id]
            kf = scs[sid].get("known_facts") if is_char else None
            pa = list(prior) if is_char else None
            old, t_old, o_old, r_old = timed(llm, annotate, r["answer"], ctx, kf, pa, by_id)
            new, t_new, o_new, r_new = timed(llm, annotate_fast, r["answer"], ctx, kf, pa, by_id)
            rows_out.append({"qid": r["qid"], "answer": r["answer"],
                             "old": {"t": t_old, "out": o_old, "think": r_old, "segments": old["segments"],
                                     "cards": [c["chunk_id"] for c in old["cards"]], "error": old["error"]},
                             "new": {"t": t_new, "out": o_new, "think": r_new, "segments": new["segments"],
                                     "cards": [c["chunk_id"] for c in new["cards"]], "error": new["error"]}})
            print(f"{r['qid']}: 지금 {t_old:.1f}s(출력 {o_old}) / 빠른 {t_new:.1f}s(출력 {o_new})  "
                  f"카드 {sorted(rows_out[-1]['old']['cards'])} / {sorted(rows_out[-1]['new']['cards'])}", flush=True)
            if is_char:
                prior.append(r["answer"])
    json.dump(rows_out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
