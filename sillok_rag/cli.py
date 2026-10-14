"""명령줄 실행기.

예)
  python -m sillok_rag.cli build-db                       # Chroma 벡터 DB 만들기 (OPENAI_API_KEY 필요)
  python -m sillok_rag.cli ask -c D2 "김문은 어떤 처벌을 받았나?"
  python -m sillok_rag.cli ask -c D1 --scene A "내일 어찌 되실 것 같소?"
  python -m sillok_rag.cli run-single -c D1                # 평가셋 v3 단발 67문항
  python -m sillok_rag.cli run-scenario -c D2 -s B         # 다회차 시나리오 B
  python -m sillok_rag.cli run-all --dry-run               # C·D1·D2 × 단발+시나리오 (키 없이 프롬프트만 점검)
  python -m sillok_rag.cli grade-sheet results/xxx.jsonl   # 사람 채점용 CSV
  python -m sillok_rag.cli summarize results/<실험 폴더>/*.jsonl   # 자동 점검 합계
  python -m sillok_rag.cli llm-grade results/xxx.jsonl     # LLM 자동 채점 → xxx.llmgrade.jsonl
  python -m sillok_rag.cli compare-grades results/xxx.llmgrade.jsonl results/xxx.human.csv  # 사람 채점과 비교
"""
import argparse
import sys
from pathlib import Path

from . import config
from .corpus import load_chunks


def make_retriever(kind: str, chunks: list[dict], llm, rerank: bool = config.RERANK,
                   check: bool = config.RERANK_CHECK, rerank_llm=None):
    from .retrieval import RerankRetriever

    base = _base_retriever(kind, chunks, llm)
    # 리랭커는 모델을 불러야 하므로 미리보기(dry-run)에서는 검색 순위를 그대로 쓴다
    if not rerank or llm.dry_run:
        return base
    return RerankRetriever(base, rerank_llm or llm, config.RERANK_CANDIDATES, check=check)


def _base_retriever(kind: str, chunks: list[dict], llm):
    from .retrieval import BM25Retriever, ChromaRetriever, HybridRetriever, gloss_extra
    from .store import chroma_matches, chroma_ready

    # 기본(auto): Chroma DB가 있으면 하이브리드(4차 실험에서 채택), 없거나 미리보기면 BM25
    if kind == "auto":
        kind = "hybrid" if (not llm.dry_run and chroma_ready()) else "bm25"
    if kind in ("chroma", "hybrid"):
        if not chroma_ready():
            sys.exit("Chroma DB가 없습니다. 먼저 `python -m sillok_rag.cli build-db` 를 실행하세요.")
        # 옛 DB로 조용히 검색하지 않게 막는다(BM25로 넘어가지도 않음: 기준선 실행이 다른 검색기로 돌면 안 됨)
        if not chroma_matches(chunks):
            sys.exit("Chroma DB가 지금 코퍼스(data/corpus.jsonl)와 다릅니다(청크·번역·시점이 바뀜). "
                     "`python -m sillok_rag.cli build-db` 로 다시 만드세요.")
        if kind == "hybrid":
            return HybridRetriever(ChromaRetriever(chunks, llm), BM25Retriever(chunks), keep_each=config.HYBRID_KEEP_EACH,
                                   extra=gloss_extra(chunks))
        return ChromaRetriever(chunks, llm)
    return BM25Retriever(chunks)


def main(argv=None):
    p = argparse.ArgumentParser(prog="sillok_rag")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, condition=True):
        if condition:
            sp.add_argument("-c", "--condition", default="C", choices=list(config.CONDITIONS))
        sp.add_argument("--retriever", default="auto", choices=["auto", "chroma", "bm25", "hybrid"])
        sp.add_argument("--dry-run", action="store_true", help="API를 부르지 않고 프롬프트 흐름만 확인")
        sp.add_argument("--top-k", type=int, default=config.TOP_K, help="C·D 조건에서 검색해 넣을 청크 수")
        sp.add_argument("--answer-model", default=config.ANSWER_MODEL, help="답변 모델")
        sp.add_argument("--rerank-model", default=config.RERANK_MODEL, help="리랭커 모델")
        sp.add_argument("--effort", choices=["none", "low", "medium", "high"], default=config.ANSWER_EFFORT,
                        help="답변 모델의 생각 수준. 생각 단계가 있는 모델(gpt-5·gpt-6 등)에만 적용")
        sp.add_argument("--rerank-effort", choices=["none", "low", "medium", "high"], default=config.RERANK_EFFORT,
                        help=f"리랭커 모델의 생각 수준(기본 {config.RERANK_EFFORT}, 답변의 --effort와 따로 정함)")
        sp.add_argument("--run", help="실험 이름. 결과를 results/<오늘 날짜>_<이름>/ 에 모음(없으면 results/<오늘 날짜>/)")
        sp.add_argument("--no-rerank", action="store_true",
                        help=f"리랭커 끄기(기본: 검색 후보 {config.RERANK_CANDIDATES}개 중 모델이 top_k개를 고르고 "
                             "질문 속 전제도 판정함, 새 코퍼스 2·3차)")

    sub.add_parser("build-db", help="corpus.jsonl(803청크)로 로컬 Chroma DB를 새로 만든다")

    sp = sub.add_parser("ask", help="질문 하나")
    common(sp)
    sp.add_argument("question")
    sp.add_argument("--scene", choices=["A", "B", "C", "D", "E"],
                    help="인물 인터뷰 장면(시나리오 설정 문구 사용). A·B·C 훈민정음, D·E 계유정난")
    sp.add_argument("--show-prompt", action="store_true")

    sp = sub.add_parser("run-single", help="단발 질문 세트 실행")
    common(sp)
    sp.add_argument("--set", default="v3", help="평가셋 이름(data/eval/<이름>.jsonl). 기본은 v3(67문항)")
    sp.add_argument("--only", nargs="*", help="특정 문항만 (예: Q1 Q8)")

    sp = sub.add_parser("run-scenario", help="다회차 시나리오 실행")
    common(sp)
    sp.add_argument("-s", "--scenario", required=True, help="A·B·C(훈민정음), D·E(계유정난·사육신)")

    sp = sub.add_parser("run-all", help="C·D1·D2 조건으로 단발 세트와 시나리오 A·B·C 실행")
    common(sp, condition=False)
    sp.add_argument("--conditions", nargs="*", default=list(config.CONDITIONS), choices=list(config.CONDITIONS))

    sp = sub.add_parser("grade-sheet", help="결과 JSONL → 채점용 CSV")
    sp.add_argument("result", type=Path)

    sp = sub.add_parser("summarize", help="결과 파일들의 자동 점검 합계")
    sp.add_argument("results", type=Path, nargs="+")

    sp = sub.add_parser("llm-grade", help="결과 JSONL을 LLM으로 채점 → <이름>.llmgrade.jsonl")
    sp.add_argument("results", type=Path, nargs="+")
    sp.add_argument("--allow-old-corpus", action="store_true",
                    help="지금과 다른 코퍼스로 만든 답도 채점(기본은 멈춤, 옛 답을 새 정답 근거로 채점하게 됨)")

    sp = sub.add_parser("compare-grades", help="LLM 채점과 사람 채점(qid, 판정 CSV)의 일치율")
    sp.add_argument("llm_grade", type=Path)
    sp.add_argument("human_csv", type=Path)

    args = p.parse_args(argv)

    from . import evaluate
    from .llm import LLM

    if args.cmd == "build-db":
        from .store import build_chroma

        n = build_chroma(LLM())
        print(f"Chroma DB 생성: {n}개 청크 → {config.CHROMA_DIR}")
        return

    if args.cmd == "grade-sheet":
        print(evaluate.write_grade_sheet(args.result))
        return

    if args.cmd == "llm-grade":
        from . import grade

        judge, chunks = LLM(model=config.JUDGE_MODEL), load_chunks()
        for r in args.results:
            print(grade.llm_grade(r, judge, chunks, allow_old_corpus=args.allow_old_corpus))
        return

    if args.cmd == "compare-grades":
        from . import grade

        c = grade.compare(args.llm_grade, args.human_csv)
        print(f"문항 {c['n']}개: 판정 일치 {c['exact']}, 통과/부분/실패 일치 {c['pass']}")
        for qid, human, llm in c["diffs"]:
            print(f"  {qid}: 사람 {human} / LLM {llm}")
        if c["skipped"]:
            print(f"※ 한쪽이라도 판정이 비었거나 다섯 가지 밖인 {len(c['skipped'])}개는 세지 않음:")
            for qid, human, llm in c["skipped"]:
                print(f"  {qid}: 사람 '{human}' / LLM '{llm}'")
        return

    if args.cmd == "summarize":
        rows = evaluate.summarize(args.results)
        cols = ["file", "condition", "kind", "n", "leak_turns", "must_missing", "fabricated_quotes", "retrieval_hit", "dry_run"]
        print("\t".join(cols))
        for r in rows:
            print("\t".join(str(r[c]) for c in cols))
        print("※ 자동 점검은 힌트입니다. 최종 판정은 채점용 CSV에 사람이 기록하세요.")
        return

    chunks = load_chunks()
    llm = LLM(model=args.answer_model, dry_run=args.dry_run, reasoning_effort=args.effort)
    rerank_llm = llm if (args.rerank_model, args.rerank_effort) == (args.answer_model, args.effort) else \
        LLM(model=args.rerank_model, dry_run=args.dry_run, reasoning_effort=args.rerank_effort)
    retriever = make_retriever(args.retriever, chunks, llm, rerank=config.RERANK and not args.no_rerank,
                               rerank_llm=rerank_llm)

    if args.cmd == "ask":
        from .chat import ChatSession

        sc = evaluate.load_all_scenarios()[args.scene] if args.scene else None
        s = ChatSession(args.condition, chunks, llm, retriever, mode="role" if sc else "fact",
                        character=sc and sc["character"], setting=sc and sc["setup"],
                        cutoff=sc and sc["cutoff"], known_facts=sc and sc.get("known_facts"),
                        top_k=args.top_k)
        t = s.ask(args.question)
        if args.show_prompt:
            print(t.messages[0]["content"], "\n" + "-" * 40)
        print(t.answer)
        print(f"\n[근거 청크] {', '.join(t.context_ids) if len(t.context_ids) < 10 else '전체 자료'}")
        return

    if args.cmd == "run-single":
        out = evaluate.run_single(args.condition, chunks, llm, retriever, args.set, args.only, top_k=args.top_k,
                                  run=args.run)
        print(out)
    elif args.cmd == "run-scenario":
        if args.scenario not in evaluate.load_all_scenarios():
            raise SystemExit(f"없는 시나리오: {args.scenario}")
        print(evaluate.run_scenario(args.condition, args.scenario, chunks, llm, retriever, top_k=args.top_k,
                                    run=args.run))
    elif args.cmd == "run-all":
        for cond in args.conditions:
            print(evaluate.run_single(cond, chunks, llm, retriever, top_k=args.top_k, run=args.run))
            for sc in ("A", "B", "C"):
                print(evaluate.run_scenario(cond, sc, chunks, llm, retriever, top_k=args.top_k, run=args.run))
    if not llm.dry_run:
        for name, m in (("답변", llm), ("리랭커", rerank_llm)) if rerank_llm is not llm else (("전체", llm),):
            u = m.usage
            print(f"토큰 사용({name}, {m.model}): 입력 {u['prompt']:,} / 출력 {u['completion']:,}"
                  f"(그중 생각 {u['reasoning']:,}) (호출 {u['calls']}회)")


if __name__ == "__main__":
    main()
