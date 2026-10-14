"""리랭커 풀이 시험 2단계(유료, 작업기록 [303]): 리랭커가 흔들린 문항(T03·HF04 v1/v1b·HF13 v1b·A4)만
풀이를 켠 리랭커로 N회씩 돌려 정답 청크를 고르는지 본다. 저장소 루트에서: python scripts/rerank_gloss_probe.py 5 출력.json"""
import json
import sys

sys.path.insert(0, ".")
from sillok_rag import config
from sillok_rag.cli import _base_retriever
from sillok_rag.corpus import known_key, load_chunks
from sillok_rag.evaluate import load_questions, load_scenarios
from sillok_rag.llm import LLM
from sillok_rag.retrieval import RerankRetriever

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
OUT = sys.argv[2]
chunks = load_chunks()
llm = LLM()
base = _base_retriever("hybrid", chunks, llm)
rr = RerankRetriever(base, LLM(model=config.RERANK_MODEL, reasoning_effort=config.RERANK_EFFORT), config.RERANK_CANDIDATES, gloss=True)
print("검색기:", rr.name)

targets = []
for s, qid in (("v3", "T03"), ("holdout_v1_20260930", "HF04"), ("holdout_v1b_20260930", "HF04"),
               ("holdout_v1b_20260930", "HF13")):
    q = {x["id"]: x for x in load_questions(s)}[qid]
    targets.append((s, qid, q["question"], set(q["gold_chunks"]), None, None))
sc = load_scenarios()["A"]
turn = next(t for t in sc["turns"] if t["id"] == "A4")
targets.append(("scenarioA", "A4", turn["user"], {"wda_12602020_001-08"}, known_key(sc["cutoff"]), sc.get("setup")))

rows = []
for s, qid, text, gold, cutoff, scene in targets:
    for i in range(N):
        hits = rr.search(text, 4, cutoff, **({"scene": scene} if scene else {}))
        tr = rr.last_trace
        pos = [j + 1 for j, c in enumerate(tr["candidates"]) if c in gold]
        picked = bool(gold & set(tr["model_ids"]))
        rows.append({"set": s, "qid": qid, "run": i + 1, "cand_pos": pos, "n_cand": len(tr["candidates"]),
                     "model_ids": tr["model_ids"], "fallback": tr["fallback"], "gold_picked": picked})
        print(f"{s[:20]:20} {qid} {i + 1}회: 후보 위치 {pos}/{len(tr['candidates'])}, 리랭커 선택 {'O' if picked else 'X'}")
u = rr.llm.usage
print("리랭커 사용량:", u)
json.dump({"retriever": rr.name, "usage": u, "rows": rows}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
