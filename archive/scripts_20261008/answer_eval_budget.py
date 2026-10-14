"""승인받은 예산 안에서 같은 평가셋의 새 답변과 기존 답변을 비교한다.

기본 실행은 무료 사전 점검이다. --allow-paid와 --budget-usd를 함께 지정해야 실행한다.
앱의 프롬프트·추론 수준·출력 제한은 바꾸지 않는다. 각 요청의 최대 출력 요금을
미리 확보하며, 실패한 요청은 그 최대 비용을 예약한 채 추가 호출을 멈춘다.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.retrieval_stage_diag import CachedEmbedder, RESULTS, database_check
from sillok_rag import config, evaluate, grade
from sillok_rag.cli import make_retriever
from sillok_rag.corpus import corpus_fingerprint, load_chunks, read_jsonl
from sillok_rag.llm import LLM

# 공식 기본 단가(100만 토큰당 달러)와 모델의 최대 출력 토큰.
RATES = {config.ANSWER_MODEL: (0.10, 0.50, 128000),
         config.JUDGE_MODEL: (0.15, 0.60, 16384),
         config.EMBED_MODEL: (0.13, 0.0, 0)}
SETS = ["v3", "holdout_v1_20260930", "holdout_v1b_20260930"]
CACHE = config.DATA_DIR / "cache/retrieval_queries_text-embedding-3-large.json"


class BudgetStop(RuntimeError):
    """예산 부족 또는 사용량이 불확실한 실패 뒤 호출 중단."""


class Budget:
    def __init__(self, limit, log_path):
        self.limit, self.log_path = limit, log_path
        self.spent, self.blocked = 0.0, False
        self.events = []

    def reserve(self, model, input_upper):
        if self.blocked:
            raise BudgetStop("앞선 호출 실패로 추가 유료 호출 중단")
        inp, out, maximum = RATES[model]
        # 캐시 쓰기 할증까지 여유를 둔다. 입력은 UTF-8 바이트 수로 넉넉히 잡는다.
        bound = (input_upper * inp * 1.25 + maximum * out) / 1_000_000
        if self.spent + bound > self.limit:
            self.blocked = True
            raise BudgetStop("다음 요청의 최대 요금까지 확보할 예산 부족")
        event = {"model": model, "reserved_usd": bound, "status": "요청 전 예약"}
        self.events.append(event)
        self.spent += bound
        self.save()
        return event

    def settle(self, event, usage):
        if usage is None:
            self.blocked = True
            event["status"] = "사용량 누락, 예약 유지 후 중단"
            self.save()
            raise BudgetStop("응답에 사용량이 없어 중단")
        inp, out, _ = RATES[event["model"]]
        prompt = getattr(usage, "prompt_tokens", getattr(usage, "total_tokens", 0))
        completion = getattr(usage, "completion_tokens", 0)
        cost = (prompt * inp + completion * out) / 1_000_000
        self.spent += cost - event["reserved_usd"]
        event.update(status="성공", input_tokens=prompt, output_tokens=completion,
                     calculated_usd=cost)
        self.save()

    def fail(self, event, exc):
        self.blocked = True
        event.update(status="실패, 예약 유지 후 중단", error_type=type(exc).__name__,
                     http_status=getattr(exc, "status_code", None))
        self.save()

    def save(self):
        self.log_path.write_text(json.dumps({"budget_usd": self.limit,
            "calculated_or_reserved_usd": self.spent, "blocked": self.blocked,
            "events": self.events}, ensure_ascii=False, indent=2), encoding="utf-8")


class BudgetLLM(LLM):
    def __init__(self, budget, **kwargs):
        super().__init__(**kwargs)
        self.budget = budget
        self._client = self._client.with_options(max_retries=0, timeout=120)

    def chat(self, messages, json_mode=False):
        upper = sum(len(json.dumps(m, ensure_ascii=False).encode("utf-8")) + 128
                    for m in messages) + 128
        event = self.budget.reserve(self.model, upper)
        try:
            # 모델 기본 최대 출력을 그대로 둔다. 별도 출력 제한을 걸지 않는다.
            resp = self._client.chat.completions.create(model=self.model, messages=messages,
                                                       **self.params(json_mode))
        except Exception as exc:
            self.budget.fail(event, exc)
            raise BudgetStop("API 실패 뒤 추가 호출 중단") from None
        self.budget.settle(event, resp.usage)
        self.usage["prompt"] += resp.usage.prompt_tokens
        self.usage["completion"] += resp.usage.completion_tokens
        self.usage["calls"] += 1
        details = getattr(resp.usage, "completion_tokens_details", None)
        self.usage["reasoning"] += getattr(details, "reasoning_tokens", None) or 0
        if self.usage["calls"] % 10 == 0:
            print(f"{self.model}: {self.usage['calls']}회, 누적 환산 ${self.budget.spent:.5f}", flush=True)
        return resp.choices[0].message.content

    def embed(self, texts):
        event = self.budget.reserve(self.embed_model,
                                    sum(len(t.encode("utf-8")) + 128 for t in texts))
        try:
            resp = self._client.embeddings.create(model=self.embed_model, input=texts)
        except Exception as exc:
            self.budget.fail(event, exc)
            raise BudgetStop("임베딩 실패 뒤 추가 호출 중단") from None
        self.budget.settle(event, resp.usage)
        return [r.embedding for r in resp.data]


def plan(chunks):
    db = database_check(chunks)
    if not db["matches"]:
        raise RuntimeError("DB 전수 비교 불일치")
    questions = [q["question"] for s in SETS for q in evaluate.load_questions(s)]
    scenarios = evaluate.load_scenarios()
    for sc in scenarios.values():
        questions += [sc["setup"]] + [t["user"] for t in sc["turns"]]
    cached = CachedEmbedder(None, CACHE)
    baseline = {k: config.RESULTS_DIR / (RESULTS[k][0] + ".jsonl")
                for k in [*SETS, "A", "B", "C"]}
    for key, path in baseline.items():
        rows = read_jsonl(path)
        for row in rows:
            for field, value in {"condition": "D2", "model": config.ANSWER_MODEL,
                "reasoning_effort": "low", "rerank_model": config.RERANK_MODEL,
                "prompt_version": "v4", "top_k": 4,
                "corpus_fp": corpus_fingerprint(chunks)}.items():
                if row.get(field) != value:
                    raise RuntimeError(f"기준선 조건 불일치: {key}, {field}")
        items = grade._items_by_qid(rows[0]["kind"])
        if any(r["qid"] not in items for r in rows if r["category"] != evaluate.SETUP_CATEGORY):
            raise RuntimeError("기준선의 채점 문항 연결 누락")
    missing = list(dict.fromkeys(t for t in questions if t not in cached.cache))
    return baseline, missing, {"answer_rows": len(questions), "scored": len(questions)-3,
        "unique_queries": len(set(questions)), "cache_missing": len(missing), "database": db,
        "baseline": {k: str(v.relative_to(config.ROOT)) for k, v in baseline.items()}}


DEFAULT_RUN = "20261001_search_answer_D2"
FOLDER = "20261001_검색보강답변평가"   # 결과 폴더(results/ 아래). 새 실행이면 main()이 --folder 또는 실행 이름으로 바꿈(작업기록 [177])


def run_file(run_name: str, suffix: str, folder: str | None = None) -> Path:
    """실행 기록은 답변 결과와 같은 실험 폴더(results/<폴더>/)에 실행 이름을 앞에 붙여 둔다(작업기록 [172], [177])."""
    return config.RESULTS_DIR / (folder or FOLDER) / f"{run_name}{suffix}"


def compare_pairs(baseline, new_paths, old_grades, new_grades, run_name):
    pairs, summary = [], {}
    for key in baseline:
        old = {r["qid"]: r for r in read_jsonl(baseline[key])}
        og = {r["qid"]: r for r in read_jsonl(old_grades[key])}
        ng = {r["qid"]: r for r in read_jsonl(new_grades[key])}
        human = grade.read_human(baseline[key].with_suffix(".human.csv"))
        for row in read_jsonl(new_paths[key]):
            qid = row["qid"]
            if qid not in ng:
                continue
            pairs.append({"set": key, "qid": qid, "category": row["category"],
                "old_verdict": og[qid]["verdict"], "new_verdict": ng[qid]["verdict"],
                "old_human": human.get(qid, ""), "old_reason": og[qid]["reason"],
                "new_reason": ng[qid]["reason"], "question": row["question"],
                "old_answer": old[qid]["answer"], "new_answer": row["answer"],
                "old_context": old[qid]["context_ids"], "new_context": row["context_ids"]})
        group = [p for p in pairs if p["set"] == key]
        summary[key] = {"n": len(group),
            "old": dict(Counter(p["old_verdict"] for p in group)),
            "new": dict(Counter(p["new_verdict"] for p in group)),
            "gained": [p["qid"] for p in group if grade.PASS.get(p["old_verdict"]) != "통과"
                       and grade.PASS.get(p["new_verdict"]) == "통과"],
            "lost": [p["qid"] for p in group if grade.PASS.get(p["old_verdict"]) == "통과"
                     and grade.PASS.get(p["new_verdict"]) != "통과"]}
    run_file(run_name, ".비교_자동채점.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with run_file(run_name, ".문항별비교.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pairs[0]))
        w.writeheader()
        w.writerows(pairs)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--budget-usd", type=float)
    parser.add_argument("--run-name", default=DEFAULT_RUN)
    parser.add_argument("--folder", help="results/ 아래 결과 폴더 이름(기본: 실행 이름과 같음, 2026-10-01 실행은 기존 폴더)")
    args = parser.parse_args(argv)
    if args.allow_paid and (args.budget_usd is None or not 0 < args.budget_usd <= 0.50):
        parser.error("승인 범위의 예산(0 초과, $0.50 이하)을 명시하세요.")
    if Path(args.run_name).name != args.run_name:
        parser.error("실행 이름에는 경로를 넣을 수 없습니다.")
    global FOLDER
    FOLDER = args.folder or (FOLDER if args.run_name == DEFAULT_RUN else args.run_name)
    if Path(FOLDER).name != FOLDER:
        parser.error("폴더 이름에는 경로를 넣을 수 없습니다.")
    chunks = load_chunks()
    baseline, missing, preflight = plan(chunks)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.allow_paid:
        return
    for key in baseline:
        out = run_file(args.run_name, f"_{key}.jsonl")
        if out.exists() or out.with_name(out.name+".part").exists():
            raise FileExistsError("새 결과를 덮어쓸 수 없습니다.")
    manifest_path = run_file(args.run_name, ".manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        raise FileExistsError("같은 이름의 실행 기록이 있습니다.")
    manifest = {**preflight, "budget_usd": args.budget_usd,
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "settings": {"condition": "D2", "prompt": config.PROMPT_VERSION,
            "answer_model": config.ANSWER_MODEL, "rerank_model": config.RERANK_MODEL,
            "effort": "low", "judge_model": config.JUDGE_MODEL, "top_k": config.TOP_K,
            "keep_each": config.HYBRID_KEEP_EACH, "output_limit_changed": False},
        "file_sha256": {str(p.relative_to(config.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [config.CORPUS_PATH, config.SCENARIOS_PATH,
                *[config.EVAL_DIR / ((config.EVAL_SET if s == "v3" else s)+".jsonl") for s in SETS],
                *baseline.values()]}}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    budget = Budget(args.budget_usd, run_file(args.run_name, ".usage.json"))
    answer = BudgetLLM(budget, model=config.ANSWER_MODEL, reasoning_effort="low")
    rerank = BudgetLLM(budget, model=config.RERANK_MODEL, reasoning_effort="low")
    cache = CachedEmbedder(answer, CACHE)
    cache.dry_run = False
    retriever = make_retriever("hybrid", chunks, cache, rerank_llm=rerank)
    if missing:
        cache.embed(missing)
    new_paths = {}
    for key in baseline:
        out = run_file(args.run_name, f"_{key}.jsonl")
        if out.exists() or out.with_name(out.name+".part").exists():
            raise FileExistsError("새 결과를 덮어쓸 수 없습니다.")
        print(f"답변 실행: {key}", flush=True)
        if key in SETS:
            new_paths[key] = evaluate.run_single("D2", chunks, answer, retriever, set_name=key, out_path=out)
        else:
            new_paths[key] = evaluate.run_scenario("D2", key, chunks, answer, retriever, out_path=out)
        print(f"답변 완료: {key}, 환산 ${budget.spent:.5f}", flush=True)
    judge = BudgetLLM(budget, model=config.JUDGE_MODEL, reasoning_effort=None)
    grades = {"old": {}, "new": {}}
    for label, paths in [("new", new_paths), ("old", baseline)]:
        for key, path in paths.items():
            print(f"채점 실행: {label}, {key}", flush=True)
            grades[label][key] = grade.llm_grade(path, judge, chunks,
                out_path=run_file(args.run_name, f"_{key}.llmgrade.jsonl" if label == "new" else f"_old_{key}.llmgrade.jsonl"))
    compare_pairs(baseline, new_paths, grades["old"], grades["new"], args.run_name)
    manifest.update(new_results={k: str(p.relative_to(config.ROOT)) for k,p in new_paths.items()},
                    usage={"answer": answer.usage, "rerank": rerank.usage, "judge": judge.usage},
                    calculated_usd=budget.spent, completed=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"실행 완료, 기본 단가 환산 ${budget.spent:.6f} (계정 청구 내역 미확인)", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except Exception as exc:
        # 키가 들어갈 수 있는 예외 원문과 traceback은 출력하지 않는다.
        print(f"실행 중단: {type(exc).__name__}, HTTP {getattr(exc, 'status_code', None)}", flush=True)
        sys.exit(1)
