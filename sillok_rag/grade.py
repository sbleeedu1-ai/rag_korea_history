"""LLM 자동 채점기와, 사람(검수자) 채점과의 비교.

- 판정 5가지는 채점표(evaluate.GRADE_COLUMNS)와 같다: 정답 / 부분 / 오답 / 적절한 보류 / 부적절한 보류.
- 채점기에게는 질문, 문항 종류, 채점 기준(expected·pass_rule), 틀린 답의 예, 정답 근거 청크의 우리 번역,
  챗봇이 실제로 본 청크(context_ids) 중 정답 근거 밖의 것(2026-09-30 추가, F42 오판 때문),
  (다회차면) 인물·장면 시점, 사실 카드(인물이 이미 아는 것), 이번 답을 한 쪽(인물/해설자), 앞선 문답을 준다
  (2026-09-30 추가: 이것들이 없으면 카드에 있는 사실을 '지어냄'으로, 해설자 설명을 인물의 누설로 오판할 수 있음).
  국역·신역·기출 원문은 넣지 않는다.
- 결과는 결과 파일 옆에 `<이름>.llmgrade.jsonl`로 새로 쓴다(덮어쓰지 않음).
- 사람 채점은 `<이름>.human.csv`(qid, 판정, 메모)로 받고, 두 채점이 얼마나 일치하는지 센다.
"""
import csv
import json
from pathlib import Path

from .corpus import corpus_fingerprint, read_jsonl
from .evaluate import SETUP_CATEGORY, load_all_scenarios, load_questions, write_when_done

VERDICTS = ["정답", "부분", "오답", "적절한 보류", "부적절한 보류"]
# 통과 여부로 묶을 때: 정답·적절한 보류는 통과, 부분은 부분, 나머지는 실패
PASS = {"정답": "통과", "적절한 보류": "통과", "부분": "부분", "오답": "실패", "부적절한 보류": "실패"}

JUDGE_SYSTEM = """당신은 조선왕조실록 기반 챗봇의 답을 채점하는 채점자입니다.
채점 기준과 정답 근거(실록 번역)를 보고 챗봇의 답을 아래 다섯 가지 중 하나로 판정하세요.

- 정답: 채점 기준의 핵심을 맞게 말함. 잘못된 전제 문항이면 전제가 틀렸다고 바로잡음. 역할 대화면 통과 조건을 지킴.
- 부분: 핵심 일부만 맞거나, 맞는 내용과 틀린 내용이 섞임. 일부만 있는 문항에서 있는 부분만 답하고 없는 부분을 지어냄.
- 오답: 틀린 내용을 말함, 잘못된 전제를 그대로 받아 지어냄, 역할 대화에서 장면 뒤의 일을 누설하거나 통과 조건을 어김.
- 적절한 보류: 자료에 없는 질문(또는 일부만 있는 문항의 없는 부분)에 "기록에서 확인되지 않는다"처럼 모른다고 함.
- 부적절한 보류: 자료에 답이 있는데(정답 근거가 있는데) 모른다·확인되지 않는다고 함.

주의:
- 채점 기준에 없는 사소한 표현 차이는 문제 삼지 않습니다. 숫자·인물·누가 한 말인지는 엄격히 봅니다.
- 일부만 있는 문항은 있는 부분을 맞게 답하고 없는 부분은 모른다고 해야 정답입니다.
- 정답 근거에도, 챗봇이 본 자료에도 없는 사실을 단정하면 감점합니다.
- 챗봇이 본 자료(정답 근거 밖)에 실제로 있는 사실을 맞게 옮긴 것은 지어낸 것이 아닙니다. 다만 질문과 관계없거나 자료를 잘못 옮겼으면 감점합니다.
- 역할 대화에서 [사실 카드]의 내용은 인물이 장면 시점에 이미 아는 것이므로 지어낸 것도 누설도 아닙니다. [앞선 대화]에서 이미 나온 내용을 이어 말한 것도 지어낸 것이 아닙니다.
- 역할 대화에서 [이번 답을 한 쪽]이 해설자이면 장면 뒤의 일을 설명해도 인물의 누설이 아닙니다. 누설은 인물이 답한 턴에서만 봅니다. 다만 인물이 앞서 해설자가 말한 뒷날 일을 자기가 아는 것처럼 이어 말하면 누설입니다.

JSON으로만 답하세요: {"verdict": "<다섯 가지 중 하나>", "reason": "<한두 문장, 한글>"}"""


def _items_by_qid(kind: str = "single") -> dict:
    """qid → 평가셋 문항(단발) 또는 시나리오 턴(+인물·시점).

    kind는 결과 행의 kind 칸이다. "single"(v3)·"scenario…"가 아니면 평가셋 이름이므로 그 파일의 문항을 읽는다.
    예전에는 v3만 읽어 검증셋 24문항이 모두 빈 문항으로 채점됐다(정답 근거·있는/없는 부분이 빠짐, 원인 분석 5-2).
    """
    set_name = "v3" if kind == "single" or kind.startswith("scenario") else kind
    items = {q["id"]: q for q in load_questions(set_name)}
    for sid, sc in load_all_scenarios().items():
        for t in sc["turns"]:
            items[t["id"]] = {**t, "character": sc["character"], "cutoff": sc["cutoff"], "setup": sc["setup"],
                              "known_facts": sc.get("known_facts", [])}
    return items


SPEAKER_KO = {"character": "인물", "narrator": "해설자", "assistant": "일반 도우미"}


def judge_messages(row: dict, item: dict, chunk_text: dict, history: list[dict] | None = None) -> list[dict]:
    """history: 같은 시나리오에서 이 턴 앞의 결과 행들(설정 턴 포함). 역할 대화에서만 쓴다."""
    lines = [f"[문항 종류] {row['category']}"]
    if "setup" in item:
        lines.append(f"[역할 대화 설정] 인물: {item['character']}, 장면 시점: {item['cutoff']}. {item['setup']}")
        if item.get("known_facts"):
            lines.append("[사실 카드(인물이 장면 시점에 이미 아는 것)]\n" + "\n".join(f"- {k['fact']}" for k in item["known_facts"]))
        if history:
            lines.append("[앞선 대화]\n" + "\n".join(
                f"{h['qid']} 질문: {h['question']}\n{h['qid']} 답({SPEAKER_KO.get(h.get('speaker'), h.get('speaker'))}): {h['answer']}"
                for h in history))
        if row.get("speaker"):
            lines.append(f"[이번 답을 한 쪽] {SPEAKER_KO.get(row['speaker'], row['speaker'])}")
    lines.append(f"[질문] {row['question']}")
    lines.append(f"[채점 기준] {row['expected']}")
    if item.get("wrong_example"):
        lines.append(f"[틀린 답의 예] {item['wrong_example']}")
    if item.get("partial"):
        lines.append(f"[있는 부분] {item['partial']['have']} / [없는 부분] {item['partial']['lack']}")
    if item.get("abstain"):
        lines.append("[참고] 이 질문의 답은 자료에 없습니다. 모른다고 해야 합니다.")
    gold_ids = item.get("gold_chunks", [])
    gold = [chunk_text[c] for c in gold_ids if c in chunk_text]
    if gold:
        lines.append("[정답 근거(실록 번역)]\n" + "\n".join(gold))
    # 챗봇이 실제로 본 청크 중 정답 근거 밖의 것. 이것이 없으면 맞게 인용한 추가 근거를 '지어냄'으로 오판한다(F42)
    seen = [chunk_text[c] for c in row.get("context_ids", []) if c in chunk_text and c not in gold_ids]
    if seen:
        lines.append("[챗봇이 본 자료(정답 근거 밖)]\n" + "\n".join(seen))
    lines.append(f"[챗봇의 답]\n{row['answer']}")
    return [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


def llm_grade(result_path: Path, llm, chunks: list[dict], out_path: Path | None = None,
              allow_old_corpus: bool = False) -> Path:
    """결과 파일 하나를 LLM으로 채점한다. 설정 턴(예: C0)은 채점하지 않는다.

    답을 만들 때의 코퍼스(결과 행의 corpus_fp)가 지금 코퍼스와 다르면 채점기를 부르기 전에 멈춘다.
    같은 청크 ID라도 번역이 바뀌었으면 옛 답을 새 정답 근거로 채점하게 된다([128]-[129], 전체검토 2-8 4번).
    일부러 그렇게 채점할 때만 allow_old_corpus=True(CLI --allow-old-corpus).
    """
    rows = read_jsonl(result_path)
    if not allow_old_corpus:
        now = corpus_fingerprint(chunks)
        old = sorted({str(r.get("corpus_fp")) for r in rows if r.get("corpus_fp") != now})
        if old:
            raise ValueError(f"{result_path.name}: 답을 만든 코퍼스({', '.join(old)})가 지금 코퍼스({now})와 다릅니다. "
                             "채점하지 않고 멈춥니다(옛 답을 일부러 채점하려면 --allow-old-corpus).")
    items = _items_by_qid(rows[0]["kind"] if rows else "single")
    missing = sorted({r["qid"] for r in rows if r["category"] != SETUP_CATEGORY and r["qid"] not in items})
    if missing:
        # 문항을 못 찾으면 정답 근거 없이 채점하게 되므로 비용을 쓰기 전에 멈춘다
        raise KeyError(f"평가셋에서 문항을 찾지 못함: {', '.join(missing)}")
    chunk_text = {c["chunk_id"]: f"{c['header']} {c['translation']}" for c in chunks}
    out_path = out_path or result_path.with_suffix(".llmgrade.jsonl")
    if out_path.exists():
        raise FileExistsError(f"{out_path} 가 이미 있습니다(채점 결과는 덮어쓰지 않음).")
    with write_when_done(out_path) as f:
        history: list[dict] = []   # 한 결과 파일은 시나리오 하나라서 앞선 행이 곧 앞선 대화다(단발은 쓰지 않음)
        for row in rows:
            if row["category"] == SETUP_CATEGORY:
                history.append(row)
                continue
            raw = llm.chat(judge_messages(row, items[row["qid"]], chunk_text, history), json_mode=True)
            history.append(row)
            try:
                got = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                got = None
            if not isinstance(got, dict):   # 목록·문자열 같은 JSON도 읽지 못한 것으로 본다(코드정리검토 X7)
                got = {"verdict": "", "reason": f"채점기 응답을 읽지 못함: {raw}"}
            verdict = got.get("verdict", "")
            f.write(json.dumps({
                "qid": row["qid"], "condition": row["condition"], "category": row["category"],
                "verdict": verdict if verdict in VERDICTS else "", "reason": got.get("reason", ""),
                "judge_model": llm.model,
            }, ensure_ascii=False) + "\n")
    return out_path


def read_human(csv_path: Path) -> dict:
    """사람 채점 CSV → {qid: 판정}. 판정 칸은 `판정`(qid,판정,메모 표)이나
    `판정(정답/부분/…)`(grade-sheet가 만든 표) 둘 다 읽는다(예전에는 앞의 것만 읽어 KeyError, 전체검토 2-8 3번)."""
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        names = reader.fieldnames or []
        col = next((c for c in names if c == "판정"), None) or next((c for c in names if c.startswith("판정(")), None)
        if col is None:
            raise KeyError(f"{csv_path.name}에 판정 칸이 없습니다(칸: {reader.fieldnames}).")
        return {r["qid"]: (r[col] or "").strip() for r in reader}


def compare(llm_path: Path, human_path: Path) -> dict:
    """두 채점의 일치율. 판정 5가지가 같은지(exact)와 통과/부분/실패로 묶었을 때 같은지(pass).

    양쪽 모두 판정 5가지 중 하나를 적은 문항만 센다. 예전에는 빈칸(미채점·채점기 오류)끼리도 일치로 세어
    일치율이 오류 없이 부풀 수 있었다(전체검토 2-8 3번). 빠진 문항은 skipped로 따로 돌려준다.
    """
    llm = {r["qid"]: r["verdict"] for r in read_jsonl(llm_path)}
    human = read_human(human_path)
    both = [q for q in human if q in llm]
    qids = [q for q in both if llm[q] in VERDICTS and human[q] in VERDICTS]
    skipped = [(q, human[q], llm[q]) for q in both if q not in qids]
    exact = sum(llm[q] == human[q] for q in qids)
    same_pass = sum(PASS[llm[q]] == PASS[human[q]] for q in qids)
    diffs = [(q, human[q], llm[q]) for q in qids if llm[q] != human[q]]
    return {"n": len(qids), "exact": exact, "pass": same_pass, "diffs": diffs, "skipped": skipped}
