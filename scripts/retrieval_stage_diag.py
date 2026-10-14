"""검색 단계 진단: 정답 청크가 어느 단계에서 빠지는지 본다(원인 분석 7절 2-3번, 작업기록 [135]).

지금 기본 검색은 '공동 평균 순위로 RRF 결합 → 상위 20개 + 각 검색기 상위 10개 → 리랭커가 4개'다.
결과 파일에는 최종 4개만 남아 있어서, 정답이 ① 두 검색기 모두 못 찾았는지 ② 합칠 때 20개 밖으로 밀렸는지
③ 후보에는 있었는데 리랭커가 버렸는지를 알 수 없었다. 이 스크립트는 실제 코드(ChromaRetriever·BM25Retriever·
HybridRetriever)를 그대로 써서 정답 청크의 단계별 순위를 출력한다.

- 답변·리랭커 모델은 부르지 않는다. 기본 실행은 캐시만 쓰며, 질문 임베딩 유료 호출은 --allow-paid로 명시한다.
- 임베딩은 캐시 파일에 저장해 다시 돌리면 API를 부르지 않는다. 청크 벡터는 로컬 chroma_db를 읽는다.
- 역할 대화 턴은 인물이 답하는 조건(D2)과 같게 장면 시점 필터를 건다. 역할 턴에는 평가셋에 정답 청크가 없어서
  아래 ROLE_GOLD에 진단용으로 적었다(사실 카드와 원인 분석 3-3 기준).
- 저장된 결과 파일(RESULTS)의 최종 4개에 정답이 있었는지도 함께 보여 준다.

실행: python scripts/retrieval_stage_diag.py [--all] [--cache 임베딩캐시.json] [--preflight | --dry-run]
  --all: 정답 청크가 있는 단발 94문항 + 진단용 정답을 지정한 역할 4턴. 봉인한 B 재료는 읽지 않는다.
  --preflight: 캐시 누락·DB 내용 일치·질문 수만 점검(무료)
  --dry-run: 임베딩 없이 BM25 순위만 출력(키 없이 확인)
  --allow-paid: 사용자 승인 뒤에만 지정. 없는 질문 임베딩을 API로 만들어 캐시에 저장한다.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sillok_rag import config  # noqa: E402
from sillok_rag.corpus import corpus_fingerprint, known_key, load_chunks, read_jsonl, search_text  # noqa: E402
from sillok_rag.evaluate import load_questions, load_scenarios  # noqa: E402
from sillok_rag.retrieval import BM25Retriever, ChromaRetriever, HybridRetriever, UNKNOWN_KEY, gloss_extra  # noqa: E402

# 원인 분석 7절 3번의 실패 6개 + 정상 대조 6개, 그리고 역할 검색 실패로 본 B1·C1
FACT = {"v3": ["F05", "F43", "F01", "F08"],
        "holdout_v1_20260930": ["HF04", "HF05", "HP01", "HF01", "HF09", "HP02"],
        "holdout_v1b_20260930": ["HF04", "HF05", "HP01", "HF01", "HF09", "HP02"]}
ROLE_GOLD = {
    "A5": ["wda_12602020_001-05"],                                   # 상소 속 '27자'
    "B1": [f"wda_12602020_001-0{i}" for i in range(1, 9)],           # 최만리 상소 본문(첫머리-6조)
    "B9": ["wda_12602020_001-05"],                                   # 28자라는 틀린 전제 → 27자
    "C1": ["wda_12602020_001-09"],                                   # 세종의 반박(같은 날 오후)
}
# 저장된 결과(원인 분석 8절의 S1·S2, A1·A2, B1a·B1b, C1a·C1b, H1-H4). results/ 아래 실험 폴더/파일 이름
RESULTS = {
    "v3": ["20260930_v2기준선/20260930-204130_single_D2_hybrid_rerank20", "20260930_v2기준선/20260930-205018_single_D2_hybrid_rerank20"],
    "A": ["20260930_v2기준선/20260930-204635_scenarioA_D2_hybrid_rerank20", "20260930_v2기준선/20260930-205537_scenarioA_D2_hybrid_rerank20"],
    "B": ["20260930_v2기준선/20260930-204745_scenarioB_D2_hybrid_rerank20", "20260930_v2기준선/20260930-205653_scenarioB_D2_hybrid_rerank20"],
    "C": ["20260930_v2기준선/20260930-204851_scenarioC_D2_hybrid_rerank20", "20260930_v2기준선/20260930-205809_scenarioC_D2_hybrid_rerank20"],
    "holdout_v1_20260930": ["20260930_검증셋v1/20260930-214337_holdout_v1_20260930_D2_hybrid_rerank20",
                            "20260930_검증셋v1/20260930-214758_holdout_v1_20260930_D2_hybrid_rerank20"],
    "holdout_v1b_20260930": ["20260930_검증셋v1/20260930-214535_holdout_v1b_20260930_D2_hybrid_rerank20",
                             "20260930_검증셋v1/20260930-215021_holdout_v1b_20260930_D2_hybrid_rerank20"],
}


class CachedEmbedder:
    """캐시만으로도 동작한다. llm을 명시했을 때만 누락된 질문을 유료 생성한다."""

    def __init__(self, llm, path: Path | None):
        self.llm, self.path = llm, path
        self.cache = json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {}
        self.api_texts = 0

    def embed(self, texts):
        new = list(dict.fromkeys(t for t in texts if t not in self.cache))
        if new:
            if self.llm is None:
                raise RuntimeError(f"캐시에 없는 질문 {len(new)}개: 유료 호출 승인 후 --allow-paid로 실행하세요.")
            self.api_texts += len(new)
            vectors = self.llm.embed(new)
            if len(vectors) != len(new):
                raise RuntimeError("질문 수와 임베딩 응답 수가 다릅니다.")
            for t, v in zip(new, vectors):
                self.cache[t] = v
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                part = self.path.with_name(self.path.name + ".part")
                part.write_text(json.dumps(self.cache), encoding="utf-8")
                part.replace(self.path)
        return [self.cache[t] for t in texts]


def targets(all_questions=False):
    """(묶음, qid, 질문, 정답 청크, 시점 키, 장면)

    장면은 실제 대화(ChatSession)가 인물 턴의 임베딩 검색어 앞과 리랭커에 붙이는 설정 문장이다.
    예전에는 진단에서 빠져 역할 턴을 실제와 다른 검색어로 쟀다(전체검토 2-8 5번, 작업기록 [183]).
    """
    for set_name, qids in FACT.items():
        by_id = {q["id"]: q for q in load_questions(set_name)}
        for qid in by_id if all_questions else qids:
            q = by_id[qid]
            if q.get("gold_chunks"):
                role = q.get("mode") == "role"
                cutoff = known_key(q.get("cutoff")) if role else None
                yield set_name, qid, q["question"], q["gold_chunks"], cutoff, (q.get("setting") if role else None)
    for sid, sc in load_scenarios().items():
        for t in sc["turns"]:
            if t["id"] in ROLE_GOLD:
                yield sid, t["id"], t["user"], ROLE_GOLD[t["id"]], known_key(sc["cutoff"]), sc.get("setup")


def database_check(chunks, path=config.CHROMA_DIR / "chroma.sqlite3"):
    """SQLite를 읽기 전용으로 열어 실제 ID·검색 본문·시점 키를 전수 대조한다. DB를 고치지 않는다."""
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        cid, dimension = db.execute("SELECT id, dimension FROM collections WHERE name = ?",
                                    ("sillok_chunks",)).fetchone()
        metadata = dict(db.execute("SELECT key, str_value FROM collection_metadata WHERE collection_id = ?",
                                   (cid,)))
        stored = {}
        for chunk_id, key, text, integer, number in db.execute(
                "SELECT e.embedding_id, m.key, m.string_value, m.int_value, m.float_value "
                "FROM embeddings e JOIN segments s ON e.segment_id = s.id "
                "JOIN embedding_metadata m ON e.id = m.id WHERE s.collection = ?", (cid,)):
            stored.setdefault(chunk_id, {})[key] = next((v for v in (text, integer, number) if v is not None), None)
    expected = {c["chunk_id"]: c for c in chunks}
    common = stored.keys() & expected.keys()
    report = {
        "corpus_fp": corpus_fingerprint(chunks), "stored_corpus_fp": metadata.get("corpus_fp"),
        "embed_model": metadata.get("embed_model"), "dimension": dimension, "stored_chunks": len(stored),
        "missing_ids": len(expected.keys() - stored.keys()), "extra_ids": len(stored.keys() - expected.keys()),
        "text_mismatches": sum(stored[i].get("chroma:document") != search_text(expected[i]) for i in common),
        "time_mismatches": sum(stored[i].get("known_key") !=
                               (UNKNOWN_KEY if expected[i]["known_key"] is None else expected[i]["known_key"])
                               for i in common),
    }
    report["matches"] = (report["embed_model"] == config.EMBED_MODEL and dimension == 3072
                         and not any(report[k] for k in ("missing_ids", "extra_ids", "text_mismatches", "time_mismatches"))
                         and report["stored_corpus_fp"] in (None, report["corpus_fp"]))
    return report


def legacy_order(dense_hits, sparse_hits, rrf_k=60):
    """검색 보강 전 순번 방식 RRF(커밋 84e7801의 부모)를 같은 검색 결과로 재현한다."""
    scores = {}
    for hits in (dense_hits, sparse_hits):
        for rank, (chunk, _) in enumerate(hits, 1):
            cid = chunk["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1 / (rrf_k + rank)
    return sorted(scores, key=lambda cid: -scores[cid])


def saved_hits(group, qid, gold):
    """저장된 결과 두 번에서 최종 4개에 정답이 있었나. 예: 'O·X'"""
    marks = []
    for name in RESULTS.get(group, []):
        p = config.RESULTS_DIR / f"{name}.jsonl"
        row = next((r for r in read_jsonl(p) if r["qid"] == qid), None) if p.exists() else None
        marks.append("-" if row is None else "O" if set(gold) & set(row["context_ids"]) else "X")
    return "·".join(marks)


def best_rank(order, gold):
    ranks = [i for i, cid in enumerate(order, 1) if cid in gold]
    return min(ranks) if ranks else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path,
                    default=config.DATA_DIR / "cache" / f"retrieval_queries_{config.EMBED_MODEL}.json",
                    help="질문 임베딩 캐시 JSON(기본: data/cache/, 로컬 전용)")
    ap.add_argument("--all", action="store_true", help="정답 청크가 있는 단발 전체 + 역할 진단 4턴")
    ap.add_argument("--preflight", action="store_true", help="캐시·DB·문항 범위만 무료 점검")
    ap.add_argument("--allow-paid", action="store_true", help="사용자 승인 후 누락된 질문 임베딩 API 호출 허용")
    ap.add_argument("--dry-run", action="store_true", help="임베딩 없이 BM25만")
    ap.add_argument("--bm25-gloss", dest="bm25_gloss", action="store_true", default=False,
                    help="하이브리드에 들어가는 기본 BM25 색인에도 쉬운 말 풀이 글을 더함(B안 시험, 기본 끔, 작업기록 [286]·[297]·[302]). "
                         "C안의 따로 도는 풀이 BM25 보충 후보(GLOSS_KEEP)는 이 옵션과 상관없이 늘 들어감")
    ap.add_argument("--no-bm25-gloss", dest="bm25_gloss", action="store_false", help="기본 BM25에 풀이 글 없이(기본값과 같음)")
    ap.add_argument("--gloss-weight", type=float, default=config.BM25_GLOSS_WEIGHT, help="풀이 글자 조각의 가중치")
    args = ap.parse_args()
    if args.allow_paid and (args.preflight or args.dry_run):
        ap.error("무료 점검 옵션과 --allow-paid는 함께 쓸 수 없습니다.")

    chunks = load_chunks()
    items = list(targets(args.all))
    # 임베딩 캐시의 열쇠는 실제 검색어(장면이 있으면 '장면 질문', ChromaRetriever.search와 같음)
    questions = list(dict.fromkeys(f"{t[5]} {t[2]}" if t[5] else t[2] for t in items))
    emb = CachedEmbedder(None, args.cache)
    missing = [q for q in questions if q not in emb.cache]
    if args.preflight:
        groups = {g: sum(t[0] == g for t in items) for g in dict.fromkeys(t[0] for t in items)}
        print(json.dumps({"groups": groups, "items": len(items), "unique_questions": len(questions),
                          "cached_questions": len(questions) - len(missing), "missing_questions": len(missing),
                          "missing_utf8_bytes": sum(len(q.encode("utf-8")) for q in missing),
                          "cache": str(args.cache), "database": database_check(chunks), "api_calls": 0},
                         ensure_ascii=False, indent=2))
        return
    if not args.dry_run and missing and not args.allow_paid:
        sys.exit(f"캐시에 없는 질문 {len(missing)}개. API 호출 없이 중단했습니다. "
                 "--preflight로 확인하고 사용자 승인 후 --allow-paid를 지정하세요.")
    n = len(chunks)
    bm = BM25Retriever(chunks, with_gloss=args.bm25_gloss, gloss_weight=args.gloss_weight)
    dense = hybrid = None
    if not args.dry_run:
        if not database_check(chunks)["matches"]:
            sys.exit("DB의 모델·ID·검색 본문·시점이 코퍼스와 다릅니다. 재구축은 별도 승인 대상입니다.")
        dense = ChromaRetriever(chunks, emb)
        if args.allow_paid and missing:
            from sillok_rag.llm import LLM

            emb.llm = LLM()
            emb.embed(missing)
        hybrid = HybridRetriever(dense, bm, keep_each=config.HYBRID_KEEP_EACH, extra=gloss_extra(chunks))

    k = config.RERANK_CANDIDATES
    print(f"청크 {n}개, 합친 순위 {k}개 + 각 검색기 상위 {config.HYBRID_KEEP_EACH}개 후보 기준. 순위는 정답 청크 중 가장 높은 것(시점 필터 뒤 순위). "
          f"'저장 최종4'는 저장된 두 번 실행에서 최종 자료 4개에 정답이 있었나(O/X).")
    print("| 묶음 | 문항 | 임베딩 | BM25 | 합친 순위 | 예전20 | 평균20 | 보강후 | 후보 수 | 저장 최종4 | 판단 |")
    print("|---|---|---:|---:|---:|---|---|---|---:|---|---|")
    totals = {}
    for group, qid, question, gold, cutoff, scene in items:
        extra = {"scene": scene} if scene else {}   # BM25는 장면을 쓰지 않음(검색기가 무시)
        sparse_hits = bm.search(question, n, cutoff)
        b = best_rank([c["chunk_id"] for c, _ in sparse_hits], gold)
        if hybrid is None:
            print(f"| {group} | {qid} | - | {b} | - | - | - | - | - | {saved_hits(group, qid, gold)} | |")
            continue
        dense_hits = dense.search(question, n, cutoff, **extra)
        d = best_rank([c["chunk_id"] for c, _ in dense_hits], gold)
        h = best_rank([c["chunk_id"] for c, _ in hybrid.search(question, n, cutoff, **extra)], gold)
        old_hit = bool(set(gold) & set(legacy_order(dense_hits, sparse_hits)[:k]))
        avg_hit = h is not None and h <= k
        # 리랭커가 실제로 받는 후보(합친 순위 상위 k + 각 검색기 상위 HYBRID_KEEP_EACH개)
        candidates = hybrid.candidates(question, k, cutoff, **extra)
        in_cand = bool(set(gold) & {c["chunk_id"] for c, _ in candidates})
        counts = totals.setdefault(group, {"n": 0, "old": 0, "avg": 0, "new": 0, "lost": [], "gained": [], "sizes": []})
        for key, value in (("n", 1), ("old", old_hit), ("avg", avg_hit), ("new", in_cand)):
            counts[key] += value
        if old_hit and not in_cand:
            counts["lost"].append(qid)
        if not old_hit and in_cand:
            counts["gained"].append(qid)
        counts["sizes"].append(len(candidates))
        saved = saved_hits(group, qid, gold)
        if in_cand and (h is None or h > k):
            note = "각 검색기 상위 보존으로 후보에 듦(합친 순위만이면 밖)"
        elif in_cand:
            note = "후보에 있음 → 빠졌다면 리랭커 선별" if "X" in saved else "후보에 있음"
        elif any(x is not None and x <= k for x in (d, b)):
            note = "한 검색기는 20위 안인데 합치며 밀림(보존 개수 밖)"
        else:
            note = "두 검색기 모두 20위 밖"
        marks = ["O" if hit else "X" for hit in (old_hit, avg_hit, in_cand)]
        print(f"| {group} | {qid} | {d} | {b} | {h} | {' | '.join(marks)} | {len(candidates)} | {saved} | {note} |")
    for group, c in totals.items():
        print(f"\n{group}: 후보 안 정답 예전 {c['old']}/{c['n']} → 공동평균 {c['avg']}/{c['n']} "
              f"→ 보강후 {c['new']}/{c['n']}, 새로 듦 {c['gained']}, 빠짐 {c['lost']}, "
              f"후보 평균 {sum(c['sizes']) / c['n']:.1f}개·최대 {max(c['sizes'])}개.")
    if not args.dry_run:
        print(f"\n임베딩 API로 보낸 질문 {emb.api_texts}개(나머지는 캐시).")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
