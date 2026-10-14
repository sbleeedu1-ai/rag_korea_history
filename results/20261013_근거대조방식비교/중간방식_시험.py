"""근거 대조 중간 방식 시험(유료): 코드가 답을 번호 붙인 문장으로 나누고, 모델은 번호·표시·근거 ID·구절만 낸다.
(답 문장을 다시 옮겨 쓰는 것만 뺌. 구절은 지금처럼 모델이 근거 글에서 골라 옮김.) 결과는 evidence_fast.json에 "mid"로 더한다."""
import glob
import json
import sys
import time

sys.path.insert(0, r"C:\sample\rag_korea_history_test")
sys.path.insert(0, sys.argv[1])
from evidence_fast import sentences, timed
from sillok_rag.corpus import load_chunks
from sillok_rag.evaluate import load_all_scenarios
from sillok_rag.evidence import EVIDENCE_RULES, cards, evidence_messages, verify
from sillok_rag.llm import LLM

MID_RULES = EVIDENCE_RULES.split("- text에는")[0].replace(
    "[답변]을 문장(또는 뜻이 나뉘는 구절) 단위로 나누고, 각 부분에 표시 하나를 붙이세요.",
    "[답변]은 번호를 붙인 문장으로 나뉘어 있습니다. 각 번호에 표시 하나를 붙이세요.") + \
    '- 답변 글을 다시 쓰지 말고 번호만 쓰세요.\n- JSON으로만 답하세요: {"labels": [{"n": 1, "label": "기록|해석|시점|창작", "source": "ID|카드|앞선 답|", "quote": "…"}]}'


def annotate_mid(llm, answer, chunks, known_facts=None, prior_answers=None, lookup=None):
    sents = sentences(answer)
    msgs = evidence_messages(answer, chunks, known_facts, prior_answers)
    msgs[0]["content"] = MID_RULES
    msgs[1]["content"] = msgs[1]["content"].rsplit("[답변]", 1)[0] + "[답변]\n" + "\n".join(
        f"{i}. {s}" for i, s in enumerate(sents, 1))
    try:
        raw = json.loads(llm.chat(msgs, json_mode=True)).get("labels") or []
        error = None
    except Exception as e:
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
    return {"segments": segments, "cards": found, "error": error}


def main(folder):
    path = folder + r"\evidence_fast.json"
    saved = {r["qid"]: r for r in json.load(open(path, encoding="utf-8"))}
    chunks = load_chunks()
    by_id = {c["chunk_id"]: c for c in chunks}
    scs = load_all_scenarios()
    llm = LLM()
    for sid in "ABCDE":
        f = sorted(glob.glob(rf"C:\sample\rag_korea_history_test\results\20261013_리랭커none\*scenario{sid}_*.jsonl"))[-1]
        prior = []
        for r in (json.loads(l) for l in open(f, encoding="utf-8")):
            is_char = r["speaker"] == "character"
            if r["qid"].endswith("0") and len(r["qid"]) == 2:
                if is_char:
                    prior.append(r["answer"])
                continue
            ctx = [by_id[c] for c in r["context_ids"] if c in by_id]
            kf = scs[sid].get("known_facts") if is_char else None
            pa = list(prior) if is_char else None
            mid, t, o, th = timed(llm, annotate_mid, r["answer"], ctx, kf, pa, by_id)
            saved[r["qid"]]["mid"] = {"t": t, "out": o, "think": th, "segments": mid["segments"],
                                      "cards": [c["chunk_id"] for c in mid["cards"]], "error": mid["error"]}
            print(f"{r['qid']}: 지금 {saved[r['qid']]['old']['t']:.1f}s / 중간 {t:.1f}s(출력 {o})", flush=True)
            if is_char:
                prior.append(r["answer"])
    json.dump(list(saved.values()), open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
