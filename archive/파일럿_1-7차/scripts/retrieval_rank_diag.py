"""검색 순위 진단: 단발 문항마다 정답 근거 청크(gold_chunks)가 유사도 순위 몇 위인지 본다.

23청크 전체를 줄 세워서, 임베딩(Chroma, text-embedding-3-small)과 BM25(글자 2-gram) 순위를 함께 기록한다.
- 5~8위: 임베더는 대충 찾음 → top_k·청킹으로 해결 가능
- 한참 아래: 임베더가 질문과 청크를 비슷하게 보지 못함
holdout 세트는 쓰지 않는다.
실행: python scripts/retrieval_rank_diag.py  → results/검색순위진단_20260929.csv
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # 아카이브 폴더 (results/가 여기 있음)
REPO = Path(__file__).resolve().parents[3]      # 저장소 맨 위 (sillok_rag 코드)
sys.path.insert(0, str(REPO))
from sillok_rag.corpus import load_chunks  # noqa: E402
from sillok_rag.evaluate import load_questions  # noqa: E402
from sillok_rag.llm import LLM  # noqa: E402
from sillok_rag.retrieval import BM25Retriever, ChromaRetriever  # noqa: E402


def ranks(retriever, query, n):
    return {c["chunk_id"]: i + 1 for i, (c, _) in enumerate(retriever.search(query, n))}


def main():
    chunks = load_chunks()
    n = len(chunks)
    emb, bm25 = ChromaRetriever(chunks, LLM()), BM25Retriever(chunks)
    out = ROOT / "results" / "검색순위진단_20260929.csv"
    rows = []
    for q in load_questions("single"):
        gold = q.get("gold_chunks") or []
        if not gold:
            continue
        re_, rb = ranks(emb, q["question"], n), ranks(bm25, q["question"], n)
        rows.append({
            "qid": q["id"], "question": q["question"], "gold_chunks": " ".join(gold),
            "임베딩 순위": " ".join(f"{g}:{re_[g]}" for g in gold),
            "임베딩 최고 순위": min(re_[g] for g in gold),
            "임베딩 전부 들어오는 순위": max(re_[g] for g in gold),
            "BM25 순위": " ".join(f"{g}:{rb.get(g, '-')}" for g in gold),
            "BM25 최고 순위": min(rb.get(g, 99) for g in gold),
            "임베딩 1~4위": " ".join(sorted(re_, key=re_.get)[:4]),
        })
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r["qid"], "| emb", r["임베딩 순위"], "| bm25", r["BM25 순위"], "| top4", r["임베딩 1~4위"])
    best = [r["임베딩 최고 순위"] for r in rows]
    for k in (4, 6, 8, 10):
        print(f"top_k {k}: 정답 청크 하나 이상 들어옴 {sum(b <= k for b in best)}/{len(best)}")
    print(out)


if __name__ == "__main__":
    main()
