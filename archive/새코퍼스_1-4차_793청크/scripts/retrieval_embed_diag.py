"""검색 진단: 임베딩 모델(small/large) × 임베딩할 글(제목·화자 포함/본문만) × BM25와 섞는 비율.

답을 만들지 않고, 단발 평가셋 중 정답 근거 청크(gold_chunks)가 있는 문항만 써서
정답 청크가 top_k 4·8·12 안에 들어오는 문항 수를 센다. chroma_db는 건드리지 않고 메모리에서 계산한다.
OpenAI 임베딩 API를 부른다(793청크 × 2가지 글 × 2모델 + 질문). 2026-09-29 결과는 작업기록 [96].
실행: python scripts/retrieval_embed_diag.py [임베딩 저장 폴더(선택, 다시 돌릴 때 API 호출을 아낌)]
"""
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))  # 어디서 실행해도 저장소를 찾게
sys.stdout.reconfigure(encoding="utf-8")
from sillok_rag.corpus import load_chunks, search_text
from sillok_rag.evaluate import load_questions
from sillok_rag.llm import LLM
from sillok_rag.retrieval import BM25Retriever
SP = sys.argv[1] if len(sys.argv) > 1 else None
chunks = load_chunks(); n = len(chunks)
ids = [c["chunk_id"] for c in chunks]
qs = [q for q in load_questions() if q.get("gold_chunks")]
texts = {"full": [search_text(c) for c in chunks], "body": [c["translation"] for c in chunks]}
def cached(name, fn):
    p = os.path.join(SP, name + ".npy") if SP else None
    if p and os.path.exists(p): return np.load(p)
    a = np.array(fn(), dtype=np.float32)
    if p: np.save(p, a)
    return a
def unit(a): return a / np.linalg.norm(a, axis=1, keepdims=True)
bm = BM25Retriever(chunks)
bm_order = [[c["chunk_id"] for c, _ in bm.search(q["question"], n)] for q in qs]
def ranks_of(order): return {c: i+1 for i, c in enumerate(order)}
def hit(orders, k):
    return sum(min(ranks_of(o)[g] for g in q["gold_chunks"]) <= k for o, q in zip(orders, qs))
def rrf(o1, o2, w1=1.0, w2=1.0, K=60):
    s = {}
    for w, o in ((w1, o1), (w2, o2)):
        for i, c in enumerate(o): s[c] = s.get(c, 0) + w / (K + i + 1)
    return sorted(s, key=lambda c: -s[c])
print(f"{'방식':<28} k4  k8  k12")
print(f"{'BM25만':<28} {hit(bm_order,4):>3} {hit(bm_order,8):>3} {hit(bm_order,12):>3}")
for model in ("text-embedding-3-small", "text-embedding-3-large"):
    llm = LLM(embed_model=model); tag = model.split("-")[-1]
    Q = unit(cached(f"q_{tag}", lambda: llm.embed([q["question"] for q in qs])))
    for variant in ("full", "body"):
        D = unit(cached(f"d_{tag}_{variant}", lambda: llm.embed(texts[variant])))
        sims = Q @ D.T
        emb_order = [[ids[j] for j in np.argsort(-row)] for row in sims]
        name = f"{tag}·{'제목포함' if variant=='full' else '본문만'}"
        print(f"{'임베딩만 '+name:<28} {hit(emb_order,4):>3} {hit(emb_order,8):>3} {hit(emb_order,12):>3}")
        for w in (1.0, 0.5):
            h = [rrf(e, b, w, 1.0) for e, b in zip(emb_order, bm_order)]
            lab = f"하이브리드 {name} 임베딩×{w}"
            print(f"{lab:<28} {hit(h,4):>3} {hit(h,8):>3} {hit(h,12):>3}")
