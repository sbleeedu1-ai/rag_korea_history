"""저장된 결과 파일의 답변에 근거 보기를 붙인다(답변을 다시 만들지 않음, 작업기록 [196]).

같은 답변에 표시만 붙이므로 근거 보기의 정확도를 따로 잴 수 있다. 출력은 results/<날짜>_<실험 이름>/<원래 이름>.evidence.jsonl.
인물 턴은 그 시나리오의 아는 사실 카드와 같은 파일 안의 앞선 인물 답을 근거로 함께 준다. 설정 응답 턴은 건너뛴다.

실행: python scripts/evidence_backfill.py results/<폴더>/*.jsonl            # 무료: 대상 턴 수만 셈
      python scripts/evidence_backfill.py results/<폴더>/*.jsonl --allow-paid --run 근거보기   # 사용자 승인 뒤
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sillok_rag.corpus import load_chunks, read_jsonl  # noqa: E402
from sillok_rag.evaluate import SETUP_CATEGORY, is_result_file, load_all_scenarios, run_dir  # noqa: E402
from sillok_rag.evidence import annotate  # noqa: E402


def targets(path: Path, scenarios: dict):
    """(행, 아는 사실 카드, 앞선 인물 답) 묶음. 시나리오 결과만 다룬다."""
    rows = read_jsonl(path)
    prior = []
    for r in rows:
        sid = r["kind"].removeprefix("scenario")
        is_char = r["speaker"] == "character"
        if r["category"] != SETUP_CATEGORY:
            yield r, (scenarios[sid].get("known_facts") if is_char else None), (list(prior) if is_char else None)
        if is_char:
            prior.append(r["answer"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path, nargs="+")
    ap.add_argument("--run", default="근거보기", help="실험 이름(results/<오늘>_<이름>/)")
    ap.add_argument("--allow-paid", action="store_true", help="사용자 승인 뒤에만. 턴마다 답변 모델 호출 1번")
    args = ap.parse_args()
    files = [p for p in args.results if is_result_file(p) and "scenario" in p.name]
    scenarios = load_all_scenarios()
    lookup = {c["chunk_id"]: c for c in load_chunks()}
    jobs = [(p, list(targets(p, scenarios))) for p in files]
    print(f"파일 {len(jobs)}개, 턴 {sum(len(j) for _, j in jobs)}개")
    if not args.allow_paid:
        print("API 호출 없이 끝냄. 사용자 승인 뒤 --allow-paid로 실행하세요.")
        return
    from sillok_rag.llm import LLM

    llm = LLM()
    out_dir = run_dir(args.run)
    out_dir.mkdir(parents=True, exist_ok=True)
    for path, items in jobs:
        out = out_dir / path.name.replace(".jsonl", ".evidence.jsonl")
        with open(out, "w", encoding="utf-8") as f:
            for r, facts, prior in items:
                ctx = [lookup[c] for c in r["context_ids"] if c in lookup]
                ev = annotate(llm, r["answer"], ctx, facts, prior, lookup)
                f.write(json.dumps({"source_file": path.as_posix(), "qid": r["qid"], "speaker": r["speaker"],
                                    "question": r["question"], "answer": r["answer"], "context_ids": r["context_ids"],
                                    "evidence_view": ev, "model": llm.model}, ensure_ascii=False) + "\n")
        print(out)
    u = llm.usage
    print(f"토큰 사용({llm.model}): 입력 {u['prompt']:,} / 출력 {u['completion']:,}(그중 생각 {u['reasoning']:,}) (호출 {u['calls']}회)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
