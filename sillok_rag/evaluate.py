"""비교 실험 실행, 자동 점검, 채점표·요약 만들기.

자동 점검은 사람이 채점할 때 볼 '힌트'일 뿐 판정이 아니다.
- leak_hits: 역할 질문에서 미래 정보 단어가 답에 나왔는가
- must_missing: 정답에 꼭 들어갈 단어 중 빠진 것 ('a|b'는 둘 중 하나)
- fabricated_quotes: 답에 있는 한자 4자 이상 구절 중 실록 원문 어디에도 없는 것
- retrieval_hit: (C·D) 정답 근거 청크(gold_chunks)가 검색 결과에 들어왔는가
"""
import csv
import json
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import config
from .chat import ChatSession
from .corpus import corpus_fingerprint, han_only, read_jsonl

SETUP_CATEGORY = "설정 응답(집계 별도)"
HAN_RUN = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0002ffff]{4,}")


def load_questions(set_name: str = config.EVAL_SET) -> list[dict]:
    if set_name == "v3":
        set_name = config.EVAL_SET
    return read_jsonl(config.EVAL_DIR / f"{set_name}.jsonl")


def load_scenarios(path: Path | None = None) -> dict:
    """시나리오 파일 하나(기본은 v3 훈민정음 A·B·C)."""
    with open(path or config.SCENARIOS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_all_scenarios() -> dict:
    """모든 사건의 시나리오(A·B·C 훈민정음 + D·E 계유정난). 시나리오 ID는 파일끼리 겹치지 않는다."""
    merged = {}
    for path in (config.SCENARIOS_PATH, config.SCENARIOS_GYEYU_PATH):
        for sid, sc in load_scenarios(path).items():
            if sid in merged:
                raise ValueError(f"시나리오 ID가 겹칩니다: {sid}")
            merged[sid] = sc
    return merged


def fabricated_quotes(answer: str, chunks: list[dict]) -> list[str]:
    source = "".join(han_only(c["original"]) for c in chunks)
    return [run for run in HAN_RUN.findall(answer) if run not in source]


def leak_hits(answer: str, terms: list[str]) -> list[str]:
    return [t for t in terms if t in answer]


def must_missing(answer: str, terms: list[str]) -> list[str]:
    return [t for t in terms if not any(alt in answer for alt in t.split("|"))]


def retrieval_hit(context_ids: list[str], gold_chunks: list[str]) -> bool | None:
    """정답 근거 청크 중 하나라도 검색됐는가. 근거 청크가 정해지지 않은 문항은 None."""
    if not gold_chunks:
        return None
    return bool(set(gold_chunks) & set(context_ids))


@contextmanager
def write_when_done(out_path: Path):
    """결과를 '<이름>.part'에 쓰다가 끝까지 쓰면 원래 이름으로 바꾼다.

    실행 중 API가 실패하면 반쯤 쓴 파일이 원래 이름으로 남아 결과처럼 보이거나,
    채점 파일이면 다시 채점할 때 '이미 있음'으로 막혔다(2026-09-29 정리, 작업기록 [105]).
    중간에 멈추면 .part 파일만 남는다. 다시 돌리면 남은 .part는 새로 쓴다.
    끝난 결과 파일은 덮어쓰지 않는다: 모델을 부르기 전과 이름을 바꾸기 직전에 확인한다(코드정리검토 X3·C19).
    """
    def refuse():
        if out_path.exists():
            raise FileExistsError(f"{out_path} 가 이미 있습니다(끝난 결과는 덮어쓰지 않음).")

    refuse()
    part = out_path.with_name(out_path.name + ".part")
    with open(part, "w", encoding="utf-8") as f:
        yield f
    refuse()
    part.replace(out_path)


def _auto_checks(answer, item, context_ids, chunks, condition):
    return {
        "leak_hits": leak_hits(answer, item.get("leak_terms", [])),
        "must_missing": must_missing(answer, item.get("must_terms", [])),
        "fabricated_quotes": fabricated_quotes(answer, chunks),
        "retrieval_hit": retrieval_hit(context_ids, item.get("gold_chunks", []))
        if condition in ("C", "D1", "D2") else None,
    }


def run_dir(run: str | None = None) -> Path:
    """한 실험의 결과를 모으는 폴더: results/<오늘 날짜>_<실험 이름>/ (이름이 없으면 results/<오늘 날짜>/).
    답변·채점·검수표가 한 폴더에 모이게 한다(작업기록 [177])."""
    if run and Path(run).name != run:
        raise ValueError("실험 이름에는 경로를 넣을 수 없습니다.")
    day = datetime.now().strftime("%Y%m%d")
    return config.RESULTS_DIR / (f"{day}_{run}" if run else day)


def _out_path(kind: str, condition: str, dry_run: bool, top_k: int = config.TOP_K,
              retriever_name: str | None = None, llm=None, run: str | None = None) -> Path:
    folder = run_dir(run)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "_dry" if dry_run else ""
    k = f"_k{top_k}" if top_k != config.TOP_K else ""   # 기본값(config.TOP_K)이 아닐 때만 파일 이름에 표시
    # 검색기가 기본(chroma 임베딩)이 아닐 때만 파일 이름에 표시 (예: _hybrid, _bm25)
    r = f"_{retriever_name}" if condition in ("C", "D1", "D2") and retriever_name not in (None, "chroma") else ""
    # 답변 모델이 기본과 다르면 모델(과 생각 수준)을 붙인다. 예: _ans-gpt-6-luna-none
    m = ""
    if llm is not None and llm.model != config.ANSWER_MODEL:
        m = f"_ans-{llm.model}" + (f"-{llm.reasoning_effort}" if llm.reasoning_effort else "")
    # 같은 초에 같은 조건으로 시작하면 이름이 겹쳤다(전체검토 2-8 2번, 코드정리검토 X3·C19).
    # 겹치면 시각 뒤에 -2, -3 …을 붙인다(끝의 _dry 등 꼬리 이름은 그대로)
    rest, n = f"_{kind}_{condition}{r}{m}{k}{suffix}.jsonl", 1
    path = folder / f"{stamp}{rest}"
    while path.exists() or path.with_name(path.name + ".part").exists():
        n += 1
        path = folder / f"{stamp}-{n}{rest}"
    return path


def run_single(condition, chunks, llm, retriever, set_name="v3",
               only: list[str] | None = None, out_path: Path | None = None, top_k: int = config.TOP_K,
               run: str | None = None) -> Path:
    """단발 질문 세트를 한 조건으로 실행한다. 질문마다 새 세션(이력 없음)."""
    questions = [q for q in load_questions(set_name) if not only or q["id"] in only]
    unknown = sorted(set(only or []) - {q["id"] for q in questions})
    if unknown:   # 오타 난 ID가 조용히 빠지지 않게 결과 파일을 만들기 전에 멈춘다(코드정리검토 X9)
        raise ValueError(f"평가셋 {set_name}에 없는 문항: {', '.join(unknown)}")
    out_path = out_path or _out_path("single" if set_name in ("v3", config.EVAL_SET) else set_name,
                                     condition, llm.dry_run, top_k, getattr(retriever, "name", None), llm, run)
    corpus_fp = corpus_fingerprint(chunks)
    with write_when_done(out_path) as f:
        for q in questions:
            session = ChatSession(condition, chunks, llm, retriever, mode=q["mode"],
                                  character=q.get("character"), setting=q.get("setting"),
                                  cutoff=q.get("cutoff"), top_k=top_k)
            t = session.ask(q["question"])
            row = {
                "kind": "single" if set_name in ("v3", config.EVAL_SET) else set_name, "qid": q["id"], "category": q["category"], "condition": condition,
                "model": llm.model, "reasoning_effort": getattr(llm, "reasoning_effort", None), "rerank_model": getattr(getattr(retriever, "llm", None), "model", None), "embed_model": llm.embed_model, "dry_run": llm.dry_run, "prompt_version": config.PROMPT_VERSION, "top_k": top_k,
                "corpus_fp": corpus_fp,   # 어느 코퍼스로 돌렸나(옛 결과를 새 코퍼스로 재채점하면 같은 ID가 다른 본문일 수 있음)
                "retriever": getattr(retriever, "name", None) if condition in ("C", "D1", "D2") else None,
                "check": t.check,
                "question": q["question"], "answer": t.answer, "speaker": t.speaker,
                "context_ids": t.context_ids, "retrieved": t.retrieved, "rerank_trace": t.rerank_trace, "search_scene": t.search_scene,
                "expected": q["expected"], "evidence": q.get("evidence", []),
                "auto": _auto_checks(t.answer, q, t.context_ids, chunks, condition),
                "time": datetime.now().isoformat(timespec="seconds"),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out_path


def run_scenario(condition, scenario_id, chunks, llm, retriever, out_path: Path | None = None,
                 top_k: int = config.TOP_K, run: str | None = None) -> Path:
    """다회차 시나리오를 한 세션으로 이어서 실행한다. 설정 문구가 0번째 턴(예: C0)."""
    sc = load_all_scenarios()[scenario_id]
    session = ChatSession(condition, chunks, llm, retriever, mode="role", character=sc["character"],
                          setting=sc["setup"], cutoff=sc["cutoff"],
                          known_facts=sc.get("known_facts"), top_k=top_k)
    turns = [{"id": f"{scenario_id}0", "check": SETUP_CATEGORY, "user": sc["setup"], "pass_rule": ""}]
    turns += sc["turns"]
    out_path = out_path or _out_path(f"scenario{scenario_id}", condition, llm.dry_run, top_k,
                                     getattr(retriever, "name", None), llm, run)
    corpus_fp = corpus_fingerprint(chunks)
    with write_when_done(out_path) as f:
        for turn in turns:
            t = session.ask(turn["user"])
            row = {
                "kind": f"scenario{scenario_id}", "qid": turn["id"], "category": turn["check"],
                "condition": condition, "model": llm.model, "reasoning_effort": getattr(llm, "reasoning_effort", None), "rerank_model": getattr(getattr(retriever, "llm", None), "model", None), "embed_model": llm.embed_model, "dry_run": llm.dry_run, "prompt_version": config.PROMPT_VERSION, "top_k": top_k,
                "corpus_fp": corpus_fp,   # 어느 코퍼스로 돌렸나(옛 결과를 새 코퍼스로 재채점하면 같은 ID가 다른 본문일 수 있음)
                "retriever": getattr(retriever, "name", None) if condition in ("C", "D1", "D2") else None,
                "check": t.check,
                "question": turn["user"], "answer": t.answer, "speaker": t.speaker,
                "context_ids": t.context_ids, "retrieved": t.retrieved, "rerank_trace": t.rerank_trace, "search_scene": t.search_scene,
                "evidence_view": t.evidence,   # 근거 보기(요청했을 때만). "evidence"는 평가셋의 정답 근거 칸
                "expected": turn["pass_rule"], "evidence": [],
                "auto": _auto_checks(t.answer, turn, t.context_ids, chunks, condition),
                "time": datetime.now().isoformat(timespec="seconds"),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out_path


GRADE_COLUMNS = ["qid", "condition", "category", "question", "answer", "expected",
                 "leak_hits", "must_missing", "fabricated_quotes", "retrieval_hit",
                 "판정(정답/부분/오답/적절한 보류/부적절한 보류)", "근거 제시(Y/N)", "오류 유형", "메모"]


def write_grade_sheet(result_path: Path, out_csv: Path | None = None) -> Path:
    """사람이 채점할 CSV. 엑셀에서 열 수 있게 utf-8-sig로 저장한다."""
    rows = read_jsonl(result_path)
    out_csv = out_csv or result_path.with_suffix(".grade.csv")
    if out_csv.exists():   # 다시 실행하면 사람이 적은 판정·메모가 빈칸으로 덮였다(전체검토 2-8 2번)
        raise FileExistsError(f"{out_csv} 가 이미 있습니다(채점표는 덮어쓰지 않음).")
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(GRADE_COLUMNS)
        for r in rows:
            a = r["auto"]
            w.writerow([r["qid"], r["condition"], r["category"], r["question"], r["answer"], r["expected"],
                        ", ".join(a["leak_hits"]), ", ".join(a["must_missing"]),
                        ", ".join(a["fabricated_quotes"]), a["retrieval_hit"], "", "", "", ""])
    return out_csv


def is_result_file(p: Path) -> bool:
    """실행 결과 파일인가. 같은 폴더의 채점 결과(<이름>.llmgrade.jsonl)·근거 보기(<이름>.evidence.jsonl)는 칸이 달라서 뺀다
    (예전에는 results/*.jsonl에 섞여 KeyError: 'auto'로 멈춤, 중간 점검 보고서)."""
    return p.suffix == ".jsonl" and not p.name.endswith((".llmgrade.jsonl", ".evidence.jsonl"))


def result_files(folder: Path) -> list[Path]:
    """폴더(실험별 하위 폴더 포함)의 실행 결과 파일. 최근 실험 폴더·최신 이름이 앞."""
    if not folder.exists():
        return []
    return sorted((p for p in folder.rglob("*.jsonl") if is_result_file(p)),
                  key=lambda p: p.relative_to(folder).as_posix(), reverse=True)


def summarize(result_paths: list[Path]) -> list[dict]:
    """결과 파일별 자동 점검 합계. 판정이 아니라 힌트다. 채점 결과 파일이 섞여 들어오면 건너뛴다."""
    table = []
    for p in (p for p in result_paths if is_result_file(Path(p))):
        rows = read_jsonl(p)
        scored = [r for r in rows if r["category"] != SETUP_CATEGORY]
        hits = [r["auto"]["retrieval_hit"] for r in scored if r["auto"]["retrieval_hit"] is not None]
        table.append({
            "file": p.name,
            "kind": rows[0]["kind"] if rows else "",
            "condition": rows[0]["condition"] if rows else "",
            "dry_run": rows[0]["dry_run"] if rows else None,
            "n": len(scored),
            "leak_turns": sum(1 for r in scored if r["auto"]["leak_hits"]),
            "must_missing": sum(1 for r in scored if r["auto"]["must_missing"]),
            "fabricated_quotes": sum(len(r["auto"]["fabricated_quotes"]) for r in scored),
            "retrieval_hit": f"{sum(hits)}/{len(hits)}" if hits else "-",
        })
    return table
