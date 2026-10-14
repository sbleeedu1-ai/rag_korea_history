"""청킹 전략별 검색 성능 비교(로드맵 3단계, 작업기록 [217]).

다른 방식으로 원문을 새로 자르면 번역을 다시 해야 해서(비용, 사람 검수 242곳을 잃음), 이미 번역·검수한 지금 청크(803개)를
**이어 붙여** 전략을 만든다. 그래서 비교는 "지금보다 크게 자르면 검색이 어떻게 되나"를 본다.

    지금      : 규칙서 v2(문단·화자·인용 단위 + 머리말) 그대로 803개
    길이 묶기 : 기사 안에서 지금 청크를 원문 400자 이상이 될 때까지 이어 붙임(9-29 '길이만' 전략의 400자 기준)
    기사 통째 : 기사 하나가 청크 하나(132개)

질문은 정답 청크가 있는 단발 문항(개발셋 v3 + 처음 보는 질문 두 벌). 답변·리랭커는 부르지 않고 검색 적중만 잰다.
묶인 청크가 정답 청크를 하나라도 담고 있으면 적중이다. 검색은 지금 코드와 같은 임베딩·BM25(날짜 색인)·RRF 결합을 쓴다.
묶을수록 한 칸에 들어가는 글이 길어지므로 상위 4개의 글자 수도 함께 본다(답변 모델이 읽는 양·비용).

- 질문 임베딩은 data/cache의 기존 캐시를 쓴다(무료). 지금 청크의 벡터는 로컬 chroma_db에서 읽는다(무료).
- 길이 묶기·기사 통째의 청크 임베딩만 새로 만든다(유료). 기본 실행은 토큰 추정만 하고, --allow-paid를 줘야 만든다.
  만든 벡터는 data/cache/에 저장해 다시 돌리면 API를 부르지 않는다.

실행: python scripts/chunk_strategy_retrieval.py              # 무료: 묶음 통계와 비용 추정
      python scripts/chunk_strategy_retrieval.py --allow-paid # 사용자 승인 뒤
출력: results/<오늘>_청킹전략검색/ (전략별 요약, 문항별 순위)
"""
import argparse
import csv
import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sillok_rag import config  # noqa: E402
from sillok_rag.corpus import load_chunks, search_text  # noqa: E402
from sillok_rag.evaluate import load_questions  # noqa: E402
from sillok_rag.retrieval import BM25Retriever, HybridRetriever  # noqa: E402
from retrieval_stage_diag import CachedEmbedder  # noqa: E402

SETS = ["v3", "holdout_v1_20260930", "holdout_v1b_20260930"]
QUERY_CACHE = ROOT / "data" / "cache" / f"retrieval_queries_{config.EMBED_MODEL}.json"
CHUNK_CACHE = ROOT / "data" / "cache" / f"strategy_chunks_{config.EMBED_MODEL}.json"
LEN_TARGET = 400        # 원문 글자 수 기준(9-29 '길이만' 전략)
MAX_EMBED_CHARS = 6000  # 임베딩 입력 한도(8,191토큰)를 넘지 않게 자르는 글자 수. 잘린 청크 수를 출력에 적는다
K_TOP = (4, 20)
BUDGETS = (1500, 3500)  # 같은 글자 양으로 비교: 결합 순위 앞에서부터 번역을 이 글자 수까지 담았을 때 정답이 들었나


def merge(group: list[dict], idx: int) -> dict:
    """지금 청크 여러 개를 하나로 잇는다. 검색 본문 모양(search_text)은 지금 청크와 같게 둔다."""
    first = group[0]
    speakers = list(dict.fromkeys(c["speaker"] for c in group))
    return {"chunk_id": f"{first['article_id']}#{idx}", "members": [c["chunk_id"] for c in group],
            "article_id": first["article_id"], "title_ko": first["title_ko"], "speaker": "·".join(speakers),
            "translation": "\n".join(c["translation"] for c in group), "original": "".join(c["original"] for c in group),
            "record_date": first.get("record_date"), "reign": first.get("reign"), "known_key": None}


def strategies(chunks: list[dict]) -> dict[str, list[dict]]:
    by_art: dict[str, list[dict]] = {}
    for c in chunks:
        by_art.setdefault(c["article_id"], []).append(c)
    current = [dict(c, members=[c["chunk_id"]]) for c in chunks]
    lengthed, whole = [], []
    for aid, cs in by_art.items():
        whole.append(merge(cs, 0))
        group, n, idx = [], 0, 0
        for c in cs:
            group.append(c)
            n += len(c["original"])
            if n >= LEN_TARGET:
                lengthed.append(merge(group, idx))
                group, n, idx = [], 0, idx + 1
        if group:
            lengthed.append(merge(group, idx))
    return {"지금": current, "길이 묶기": lengthed, "기사 통째": whole}


def embed_text(unit: dict) -> str:
    return search_text(unit)[:MAX_EMBED_CHARS]


class MemDense:
    """임베딩 검색(코사인). ChromaRetriever와 같은 search 모양."""
    name = "dense"

    def __init__(self, units, vectors, query_embedder):
        self.units, self.query_embedder = units, query_embedder
        self.vecs = [self._norm(v) for v in vectors]

    @staticmethod
    def _norm(v):
        s = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / s for x in v]

    def search(self, query, k, max_known=None, scene=None):
        q = self._norm(self.query_embedder.embed([query])[0])
        scored = [(u, sum(a * b for a, b in zip(q, v))) for u, v in zip(self.units, self.vecs)]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]


def current_vectors(units):
    """지금 청크의 벡터는 로컬 chroma_db에 이미 있다(무료)."""
    from sillok_rag.store import open_collection

    got = open_collection().get(ids=[u["chunk_id"] for u in units], include=["embeddings"])
    by_id = dict(zip(got["ids"], got["embeddings"]))
    return [list(by_id[u["chunk_id"]]) for u in units]


def first_hit(hits, gold):
    for rank, (unit, _) in enumerate(hits, 1):
        if gold & set(unit["members"]):
            return rank
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-paid", action="store_true", help="사용자 승인 뒤에만. 묶은 청크의 임베딩을 만든다")
    args = ap.parse_args()

    chunks = load_chunks()
    strat = strategies(chunks)
    questions = [(s, q) for s in SETS for q in load_questions(s) if q.get("gold_chunks")]
    cache = json.loads(CHUNK_CACHE.read_text(encoding="utf-8")) if CHUNK_CACHE.exists() else {}
    print(f"질문 {len(questions)}개(정답 청크가 있는 단발: {', '.join(SETS)})")
    need = []
    for name, units in strat.items():
        lens = [len(u["translation"]) for u in units]
        cut = sum(len(search_text(u)) > MAX_EMBED_CHARS for u in units)
        print(f"- {name}: {len(units)}개, 번역 평균 {sum(lens) / len(lens):.0f}자(최장 {max(lens):,}자), 임베딩 때 잘림 {cut}개")
        if name != "지금":
            need += [embed_text(u) for u in units if embed_text(u) not in cache]
    chars = sum(len(t) for t in need)
    print(f"새로 만들 임베딩 {len(need)}개, {chars:,}자 ≈ 최대 {chars:,}토큰(한국어 1자 ≈ 1토큰 이하로 잡음)"
          f" → 약 ${chars / 1e6 * 0.13:.3f} 이하(text-embedding-3-large $0.13/100만 토큰)")
    if need and not args.allow_paid:
        print("API 호출 없이 끝냄. 사용자 승인 뒤 --allow-paid로 실행하세요.")
        return

    from sillok_rag.llm import LLM

    llm = LLM()
    if need:
        vecs = llm.embed(need)
        cache.update(zip(need, vecs))
        CHUNK_CACHE.parent.mkdir(parents=True, exist_ok=True)
        CHUNK_CACHE.write_text(json.dumps(cache), encoding="utf-8")
        print(f"임베딩 {len(need)}개 저장 → {CHUNK_CACHE}")
    query_embedder = CachedEmbedder(None, QUERY_CACHE)   # 질문은 캐시만(없으면 오류로 멈춤, 유료 호출 없음)

    out_dir = ROOT / "results" / f"{date.today():%Y%m%d}_청킹전략검색"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary, per_q = [], []
    for name, units in strat.items():
        vectors = current_vectors(units) if name == "지금" else [cache[embed_text(u)] for u in units]
        dense, sparse = MemDense(units, vectors, query_embedder), BM25Retriever(units)
        hybrid = HybridRetriever(dense, sparse, keep_each=10)
        stats = {f"{r}@{k}": 0 for r in ("임베딩", "BM25", "결합") for k in K_TOP}
        top4_chars = []
        for set_name, q in questions:
            gold = set(q["gold_chunks"])
            row = {"전략": name, "세트": set_name, "qid": q["id"]}
            for label, retriever in (("임베딩", dense), ("BM25", sparse), ("결합", hybrid)):
                hits = retriever.search(q["question"], len(units))
                rank = first_hit(hits, gold)
                row[f"{label} 순위"] = rank or ""
                for k in K_TOP:
                    stats[f"{label}@{k}"] += bool(rank and rank <= k)
                if label == "결합":
                    top4_chars.append(sum(len(u["translation"]) for u, _ in hits[:4]))
                    for budget in BUDGETS:  # 묶을수록 한 칸이 길어 '상위 4개'가 유리하므로 글자 양을 맞춰 본다
                        used, ok = 0, False
                        for u, _ in hits:
                            used += len(u["translation"])
                            if used > budget and ok is False and used - len(u["translation"]) > 0:
                                break
                            if gold & set(u["members"]):
                                ok = True
                                break
                        stats[f"결합 {budget:,}자 안"] = stats.get(f"결합 {budget:,}자 안", 0) + ok
            per_q.append(row)
        n = len(questions)
        summary.append({"전략": name, "청크 수": len(units), "질문 수": n,
                        **{key: f"{v}/{n}" for key, v in stats.items()},
                        "결합 상위 4개 평균 글자 수": round(sum(top4_chars) / n)})
        print(f"{name}: " + ", ".join(f"{k} {v}/{n}" for k, v in stats.items()) +
              f", 상위 4개 평균 {round(sum(top4_chars) / n):,}자")
    for fname, rows in (("전략별요약.csv", summary), ("문항별순위.csv", per_q)):
        with open(out_dir / fname, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"→ {out_dir}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
