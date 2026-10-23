"""중간 방식 근거 대조의 생각 수준 low·none 시험(유료, 20턴씩). 결과는 세방식_결과.json에 mid_low·mid_none으로 더한다."""
import glob
import json
import sys

sys.path.insert(0, r"C:\WORK\rag_korea_history_test")
sys.path.insert(0, sys.argv[1])
from evidence_fast import timed
from evidence_mid import annotate_mid
from sillok_rag.corpus import load_chunks
from sillok_rag.evaluate import load_all_scenarios
from sillok_rag.llm import LLM

PICK = {"A1", "A2", "A3", "A5", "B1", "B5", "B8", "B9", "C1", "C4", "C5", "C6",
        "D2", "D6", "D7", "D9", "E1", "E2", "E9", "E10"}


def main(folder, path):
    saved = {r["qid"]: r for r in json.load(open(path, encoding="utf-8"))}
    by_id = {c["chunk_id"]: c for c in load_chunks()}
    scs = load_all_scenarios()
    llms = {"mid_low": LLM(reasoning_effort="low"), "mid_none": LLM(reasoning_effort="none")}
    for sid in "ABCDE":
        f = sorted(glob.glob(rf"C:\WORK\rag_korea_history_test\results\20261013_리랭커none\*scenario{sid}_*.jsonl"))[-1]
        prior = []
        for r in (json.loads(l) for l in open(f, encoding="utf-8")):
            is_char = r["speaker"] == "character"
            if r["qid"] in PICK:
                ctx = [by_id[c] for c in r["context_ids"] if c in by_id]
                kf = scs[sid].get("known_facts") if is_char else None
                pa = list(prior) if is_char else None
                line = [r["qid"], f"medium {saved[r['qid']]['mid']['t']:.1f}s"]
                for key, llm in llms.items():
                    ev, t, o, th = timed(llm, annotate_mid, r["answer"], ctx, kf, pa, by_id)
                    saved[r["qid"]][key] = {"t": t, "out": o, "think": th, "segments": ev["segments"],
                                            "cards": [c["chunk_id"] for c in ev["cards"]], "error": ev["error"]}
                    line.append(f"{key[4:]} {t:.1f}s(출력 {o}, 생각 {th})")
                print(" / ".join(line), flush=True)
            if is_char:
                prior.append(r["answer"])
    json.dump(list(saved.values()), open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
