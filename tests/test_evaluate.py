import json

import pytest

from sillok_rag import config, evaluate
from sillok_rag.corpus import load_chunks
from sillok_rag.llm import LLM
from sillok_rag.retrieval import BM25Retriever

chunks = load_chunks()


def test_run_single_dry_run(tmp_path):
    out = evaluate.run_single("D1", chunks, LLM(dry_run=True), BM25Retriever(chunks), out_path=tmp_path / "r.jsonl")
    rows = [json.loads(l) for l in open(out, encoding="utf-8")]
    assert len(rows) == 67 and rows[0]["model"] == config.ANSWER_MODEL   # 평가셋 v3 단발
    csv_path = evaluate.write_grade_sheet(out)
    assert csv_path.exists()


class FailingLLM:
    """n번째 호출부터 실패하는 가짜 모델(API 실패 흉내)."""
    model, embed_model, dry_run = "fake", "fake", False

    def __init__(self, fail_at):
        self.n, self.fail_at = 0, fail_at

    def chat(self, messages, json_mode=False):
        self.n += 1
        if self.n >= self.fail_at:
            raise ConnectionError("API 실패")
        return json.dumps({"verdict": "정답", "reason": ""}) if json_mode else "답"


def test_interrupted_run_leaves_only_part_file(tmp_path):
    """실행이 중간에 멈추면 원래 이름의 파일은 생기지 않고 .part만 남는다. 다시 돌리면 정상으로 끝난다."""
    from sillok_rag import grade

    out = tmp_path / "r.jsonl"
    with pytest.raises(ConnectionError):
        evaluate.run_single("D2", chunks, FailingLLM(10), BM25Retriever(chunks), out_path=out)
    assert not out.exists() and (tmp_path / "r.jsonl.part").exists()
    evaluate.run_single("D2", chunks, FailingLLM(10**6), BM25Retriever(chunks), out_path=out)
    assert len(out.read_text(encoding="utf-8").splitlines()) == 67
    # 채점도 같다: 멈춘 채점 파일이 남아 다시 채점을 막지 않는다
    with pytest.raises(ConnectionError):
        grade.llm_grade(out, FailingLLM(5), chunks)
    g = grade.llm_grade(out, FailingLLM(10**6), chunks)
    assert len(g.read_text(encoding="utf-8").splitlines()) == 67


def test_empty_model_answer_does_not_stop_run(tmp_path):
    """모델이 빈 답(content=None)을 주면 빈 답으로 기록하고 실행을 이어 간다(코드정리검토 C1·X11).
    예전에는 자동 점검의 `t in answer`에서 TypeError로 실행 전체가 멈췄다."""
    from types import SimpleNamespace

    def create(**kwargs):
        msg = SimpleNamespace(content=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="length")], usage=None)

    llm = LLM(dry_run=True)
    llm.dry_run = False
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    out = evaluate.run_single("D2", chunks, llm, BM25Retriever(chunks), only=["F01", "F02"], out_path=tmp_path / "r.jsonl")
    rows = [json.loads(l) for l in open(out, encoding="utf-8")]
    assert [r["answer"] for r in rows] == ["", ""] and rows[0]["auto"]["must_missing"]


def test_finished_result_is_not_overwritten(tmp_path, monkeypatch):
    """끝난 결과 파일은 덮어쓰지 않고, 같은 초·같은 조건으로 시작하면 이름을 달리한다(코드정리검토 X3·C19)."""
    out = tmp_path / "r.jsonl"
    out.write_text("끝난 결과\n", encoding="utf-8")
    llm = FailingLLM(10**6)
    with pytest.raises(FileExistsError):
        evaluate.run_single("D2", chunks, llm, BM25Retriever(chunks), only=["F01"], out_path=out)
    assert out.read_text(encoding="utf-8") == "끝난 결과\n" and llm.n == 0   # 모델을 부르기 전에 멈춤
    from datetime import datetime

    class FixedTime:   # 세 번 모두 같은 초에 시작한 것처럼
        @staticmethod
        def now():
            return datetime(2026, 10, 8, 9, 0, 0)

    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(evaluate, "datetime", FixedTime)
    a = evaluate._out_path("single", "D2", True, run="충돌")
    a.write_text("", encoding="utf-8")
    b = evaluate._out_path("single", "D2", True, run="충돌")
    b.with_name(b.name + ".part").write_text("", encoding="utf-8")
    c = evaluate._out_path("single", "D2", True, run="충돌")
    assert [a.name, b.name, c.name] == ["20261008-090000_single_D2_dry.jsonl", "20261008-090000-2_single_D2_dry.jsonl",
                                        "20261008-090000-3_single_D2_dry.jsonl"]


def test_scenario_setup_turn_is_excluded_from_summary(tmp_path):
    out = evaluate.run_scenario("D2", "C", chunks, LLM(dry_run=True), BM25Retriever(chunks), out_path=tmp_path / "s.jsonl")
    rows = [json.loads(l) for l in open(out, encoding="utf-8")]
    assert rows[0]["qid"] == "C0" and len(rows) == 11
    assert evaluate.summarize([out])[0]["n"] == 10


def test_llm_grade_and_compare(tmp_path):
    from sillok_rag import grade

    out = evaluate.run_scenario("D2", "C", chunks, LLM(dry_run=True), BM25Retriever(chunks), out_path=tmp_path / "s.jsonl")
    g = grade.llm_grade(out, LLM(dry_run=True), chunks)
    rows = [json.loads(l) for l in open(g, encoding="utf-8")]
    assert len(rows) == 10 and rows[0]["qid"] == "C1"   # 설정 턴(C0)은 채점하지 않음
    with pytest.raises(FileExistsError):                  # 채점 결과는 덮어쓰지 않음
        grade.llm_grade(out, LLM(dry_run=True), chunks)
    human = tmp_path / "s.human.csv"
    human.write_text("qid,판정,메모\nC1,정답,\nC2,오답,\n", encoding="utf-8-sig")
    c = grade.compare(g, human)
    # dry-run 채점기는 판정을 비워 둔다. 빈칸은 일치·불일치 어느 쪽으로도 세지 않고 따로 알린다(전체검토 2-8 3번)
    assert c["n"] == 0 and c["exact"] == 0 and len(c["skipped"]) == 2


def test_compare_counts_only_real_verdicts(tmp_path):
    """빈칸끼리·잘못된 판정값은 일치로 세지 않는다. 예전에는 양쪽 빈칸이 '일치'로 들어가 일치율이 부풀었다."""
    from sillok_rag import grade

    g = tmp_path / "x.llmgrade.jsonl"
    g.write_text("".join(json.dumps({"qid": q, "verdict": v}, ensure_ascii=False) + "\n"
                         for q, v in [("Q1", "정답"), ("Q2", ""), ("Q3", "부분"), ("Q4", "정답")]), encoding="utf-8")
    human = tmp_path / "x.human.csv"
    human.write_text("qid,판정,메모\nQ1,정답,\nQ2,,\nQ3,오답,\nQ4,정답임,\n", encoding="utf-8-sig")
    c = grade.compare(g, human)
    assert (c["n"], c["exact"], c["pass"]) == (2, 1, 1)
    assert [q for q, _, _ in c["skipped"]] == ["Q2", "Q4"]


def test_grade_sheet_round_trip_and_no_overwrite(tmp_path):
    """grade-sheet가 만든 표(긴 판정 칸)를 채우면 compare가 읽는다. 다시 만들면 채운 표를 덮지 않고 멈춘다."""
    import csv

    from sillok_rag import grade

    out = evaluate.run_scenario("D2", "C", chunks, LLM(dry_run=True), BM25Retriever(chunks), out_path=tmp_path / "s.jsonl")
    sheet = evaluate.write_grade_sheet(out)
    rows = list(csv.reader(open(sheet, encoding="utf-8-sig")))
    col = rows[0].index("판정(정답/부분/오답/적절한 보류/부적절한 보류)")
    for r in rows[1:]:
        r[col] = "정답"
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    assert set(grade.read_human(sheet).values()) == {"정답"}
    with pytest.raises(FileExistsError):
        evaluate.write_grade_sheet(out)
    assert set(grade.read_human(sheet).values()) == {"정답"}   # 채운 판정이 그대로


def test_llm_grade_stops_on_other_corpus(tmp_path):
    """답을 만든 코퍼스와 지금 코퍼스가 다르면 채점기를 부르기 전에 멈춘다(전체검토 2-8 4번)."""
    from sillok_rag import grade

    out = evaluate.run_scenario("D2", "C", chunks, LLM(dry_run=True), BM25Retriever(chunks), out_path=tmp_path / "s.jsonl")
    rows = [json.loads(l) for l in open(out, encoding="utf-8")]
    for r in rows:
        r["corpus_fp"] = "옛지문"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    class Spy(LLM):
        def chat(self, *a, **k):
            pytest.fail("코퍼스가 다른데 채점기를 불렀습니다.")

    with pytest.raises(ValueError, match="코퍼스"):
        grade.llm_grade(out, Spy(dry_run=True), chunks)
    assert not out.with_suffix(".llmgrade.jsonl").exists()
    g = grade.llm_grade(out, LLM(dry_run=True), chunks, allow_old_corpus=True)   # 일부러 할 때만
    assert g.exists()


def test_judge_prompt_has_gold_translation_only():
    from sillok_rag import grade

    item = {q["id"]: q for q in evaluate.load_questions()}["F01"]
    row = {"category": "사실", "question": item["question"], "expected": item["expected"], "answer": "모름"}
    text = grade.judge_messages(row, item, {"waa_000083-01": "번역문"})[1]["content"]
    assert "[정답 근거(실록 번역)]\n번역문" in text
    assert "챗봇이 본 자료" not in text   # context_ids가 없으면 붙이지 않는다


def test_judge_prompt_includes_chunks_the_bot_saw():
    """채점기가 정답 근거만 보면, 챗봇이 본 다른 청크를 맞게 인용한 답을 '지어냄'으로 오판한다(F42, 중간 점검 보고서)."""
    from sillok_rag import grade

    item = {q["id"]: q for q in evaluate.load_questions()}["F01"]
    row = {"category": "사실", "question": item["question"], "expected": item["expected"], "answer": "답",
           "context_ids": ["waa_000083-01", "waa_000083-02"]}
    text = grade.judge_messages(row, item, {"waa_000083-01": "정답번역", "waa_000083-02": "추가번역"})[1]["content"]
    assert "[정답 근거(실록 번역)]\n정답번역" in text
    assert "[챗봇이 본 자료(정답 근거 밖)]\n추가번역" in text and text.count("정답번역") == 1


def test_role_judge_prompt_has_cards_speaker_and_history():
    """역할 대화 채점기가 사실 카드·답한 쪽·앞선 문답을 못 보면, 카드 내용을 '지어냄'으로, 해설자 설명을
    인물의 누설로 오판할 수 있다(2026-09-30 일일 검토 4-2)."""
    from sillok_rag import grade

    items = grade._items_by_qid()
    item = items["A5"]
    assert item["known_facts"] and "7명" in item["known_facts"][0]["fact"]
    prev = [{"qid": "A0", "question": "설정", "answer": "인사", "speaker": "character"},
            {"qid": "A4", "question": "앞 질문", "answer": "앞 답", "speaker": "narrator"}]
    row = {"category": "세부", "question": "몇 자?", "expected": "27자", "answer": "27자요", "speaker": "character"}
    text = grade.judge_messages(row, item, {}, prev)[1]["content"]
    assert "[사실 카드(인물이 장면 시점에 이미 아는 것)]" in text and "7명" in text
    assert "A4 답(해설자): 앞 답" in text and "A0 질문: 설정" in text
    assert "[이번 답을 한 쪽] 인물" in text
    single = grade.judge_messages({"category": "사실", "question": "q", "expected": "e", "answer": "a", "speaker": "assistant"},
                                  items["F01"], {}, prev)[1]["content"]
    assert "앞선 대화" not in single and "사실 카드" not in single   # 단발 문항에는 붙이지 않는다


def test_scenario_grading_passes_earlier_turns(tmp_path):
    from sillok_rag import grade

    out = evaluate.run_scenario("D2", "C", chunks, LLM(dry_run=True), BM25Retriever(chunks), out_path=tmp_path / "s.jsonl")
    rows = [json.loads(l) for l in open(out, encoding="utf-8")]
    assert rows[0]["corpus_fp"] and len({r["corpus_fp"] for r in rows}) == 1   # 어느 코퍼스로 돌렸는지 남긴다
    seen = []

    class Spy(LLM):
        def chat(self, messages, **kw):
            seen.append(messages[1]["content"])
            return "{}"

    grade.llm_grade(out, Spy(dry_run=True), chunks)
    assert "[앞선 대화]" in seen[0] and "C0 질문" in seen[0] and "C1 질문" not in seen[0]
    assert "C9 질문" in seen[-1]


def test_summary_skips_grade_files(tmp_path):
    """results/*.jsonl에 채점 결과(.llmgrade.jsonl)가 섞여도 요약·화면이 멈추지 않는다(예전에는 KeyError: 'auto')."""
    from sillok_rag import grade

    out = evaluate.run_scenario("D2", "C", chunks, LLM(dry_run=True), BM25Retriever(chunks), out_path=tmp_path / "s.jsonl")
    g = grade.llm_grade(out, LLM(dry_run=True), chunks)
    assert evaluate.result_files(tmp_path) == [out]
    table = evaluate.summarize(sorted(tmp_path.glob("*.jsonl")))   # README의 results/*.jsonl처럼
    assert [r["file"] for r in table] == [out.name] and g.exists()


def test_results_grouped_by_experiment_folder(tmp_path, monkeypatch):
    """결과는 results/<날짜>_<실험 이름>/ 에 쌓이고, 목록은 하위 폴더까지 찾되 채점 파일은 뺀다(작업기록 [177])."""
    from datetime import datetime

    from sillok_rag import grade

    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    out = evaluate.run_scenario("D2", "A", chunks, LLM(dry_run=True), BM25Retriever(chunks), run="시험")
    assert out.parent == tmp_path / f"{datetime.now():%Y%m%d}_시험"
    grade.llm_grade(out, LLM(dry_run=True), chunks)
    old = tmp_path / "20260930_예전" / "20260930-000000_single_D2.jsonl"
    old.parent.mkdir()
    old.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    assert evaluate.result_files(tmp_path) == [out, old]   # 최근 실험 폴더가 앞
    with pytest.raises(ValueError):
        evaluate.run_dir("../밖")


@pytest.mark.parametrize("set_name", ["holdout_v1_20260930", "holdout_v1b_20260930"])
def test_holdout_grading_gets_gold_and_partial(tmp_path, set_name):
    """검증셋 결과를 채점할 때도 그 평가셋의 정답 근거·있는/없는 부분이 채점기에 간다.
    예전에는 v3 문항만 읽어 검증셋 24문항이 모두 빈 문항으로 채점됐다(원인 분석 5-2)."""
    from sillok_rag import grade

    out = evaluate.run_single("D2", chunks, LLM(dry_run=True), BM25Retriever(chunks), set_name=set_name,
                              only=["HF04", "HP01"], out_path=tmp_path / "h.jsonl")
    seen = {}

    class Spy(LLM):
        def chat(self, messages, **kw):
            text = messages[1]["content"]
            seen["HF04" if "간경도감" in text or "불경" in text else "HP01"] = text
            return "{}"

    grade.llm_grade(out, Spy(dry_run=True), chunks)
    assert "[정답 근거(실록 번역)]" in seen["HF04"]
    assert "[있는 부분]" in seen["HP01"] and "[정답 근거(실록 번역)]" in seen["HP01"]


def test_grading_stops_on_unknown_question(tmp_path):
    """평가셋에서 문항을 못 찾으면 근거 없이 채점하지 않고 비용을 쓰기 전에 멈춘다."""
    from sillok_rag import grade

    out = evaluate.run_single("D2", chunks, LLM(dry_run=True), BM25Retriever(chunks), only=["F01"],
                              out_path=tmp_path / "r.jsonl")
    rows = [json.loads(l) for l in open(out, encoding="utf-8")]
    rows[0]["qid"] = "없는문항"
    out.write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(KeyError):
        grade.llm_grade(out, LLM(dry_run=True), chunks)
    assert not out.with_suffix(".llmgrade.jsonl").exists()


def test_run_single_stops_on_unknown_only_id(tmp_path):
    """--only에 오타 난 문항이 있으면 결과 파일을 만들기 전에 멈춘다(코드정리검토 X9)."""
    out = tmp_path / "r.jsonl"
    with pytest.raises(ValueError, match="없는문항"):
        evaluate.run_single("C", chunks, LLM(dry_run=True), BM25Retriever(chunks), only=["Q1", "없는문항"], out_path=out)
    assert not out.exists()


class ListJudge:
    """JSON이지만 객체가 아닌 값(목록)을 돌려주는 가짜 채점기."""
    model, dry_run = "fake", False

    def chat(self, messages, json_mode=False):
        return "[1, 2]"


def test_llm_grade_survives_non_object_json(tmp_path):
    from sillok_rag import grade

    out = evaluate.run_scenario("D2", "C", chunks, LLM(dry_run=True), BM25Retriever(chunks), out_path=tmp_path / "s.jsonl")
    rows = [json.loads(l) for l in open(grade.llm_grade(out, ListJudge(), chunks), encoding="utf-8")]
    assert len(rows) == 10 and rows[0]["verdict"] == "" and "읽지 못함" in rows[0]["reason"]


def test_ask_accepts_gyeyu_scene(capsys):
    """ask --scene이 계유정난 장면 D·E도 받는다(코드정리검토 C14)."""
    from sillok_rag import cli

    cli.main(["ask", "-c", "D2", "--scene", "D", "--dry-run", "--show-prompt", "지금 어디로 가시오?"])
    assert "[DRY-RUN]" in capsys.readouterr().out


def test_blank_api_key_counts_as_missing(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        LLM()
