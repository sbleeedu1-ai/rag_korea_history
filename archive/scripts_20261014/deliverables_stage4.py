"""4단계 산출물(평가셋·채점표)을 사람이 보는 엑셀 시트로 만든다(작업기록 [220]).

평가셋 원본(data/eval/*.jsonl·json)과 채점 원본(results/ 아래 CSV)은 코드가 읽는 형식이라 그대로 두고,
여기서 줄 목록을 만들어 office_export.csv_sheets_to_xlsx로 넘긴다. collect_deliverables.py가 부른다.

채점표는 중간점검 PDF의 숫자와 맞는 실행을 쓴다(모두 2026-10-01, 사실·역할 규칙 v8로 바꾸기 전):
- 사실 질문·처음 보는 질문: 검색 보강 답변 평가의 Claude 엄격 검수([161])
- 인물 대화(훈민정음): 역할 장면 검색 2회([183])
- 새 사건 대화(계유정난·사육신): 새 문항 2회([188])
"""
import ast
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"
GRADE_CSV = ROOT / "results" / "20261001_검색보강답변평가" / "20261001_search_answer_D2.검수.csv"
ROLE_RUNS = {"인물 대화(훈민정음)": ("20261001_역할장면검색", "ABC"),
             "새 사건 대화(계유정난)": ("20261001_계유정난_새문항", "DE")}
HUMAN_CMP = ROOT / "results" / "20261002_사람채점비교" / "사람채점비교_표본30_20261002.csv"
SET_NAME = {"v3": "사실 질문", "holdout_v1_20260930": "처음 보는 질문(용어 있는 말)",
            "holdout_v1b_20260930": "처음 보는 질문(쉬운 말)"}
THREE = {"정답": "정답", "적절한 보류": "정답", "부분": "부분", "오답": "오답", "부적절한 보류": "오답"}


def _chunks():
    return {json.loads(l)["chunk_id"]: json.loads(l) for l in open(ROOT / "data" / "corpus.jsonl", encoding="utf-8")}


def _where(ids, chunks) -> str:
    """정답 청크 ID → 사람이 읽는 근거 위치(재위년·날짜·제목·몇 번째 청크)."""
    out = []
    for cid in ids:
        c = chunks.get(cid)
        if not c:
            out.append(cid)
            continue
        n = int(cid.rsplit("-", 1)[1])
        out.append(f"{c.get('reign') or ''} {c['record_date'] or '총서'} 「{c['title_ko']}」 {n}번째 청크 ({cid})")
    return "\n".join(out) or "없음(자료에 없다고 해야 함)"


def _jsonl(name):
    return [json.loads(l) for l in open(EVAL / name, encoding="utf-8")]


def eval_sheets():
    chunks = _chunks()
    overview = [["묶음", "문항 수", "쓰는 방식", "원본 파일"],
                ["사실 질문", 67, "개발용: 검색·규칙·모델을 고칠 때마다 반복해서 돌려 본 문항", "data/eval/v3_20260929_한능검코퍼스+함정보강.jsonl"],
                ["인물 대화(훈민정음)", "30턴", "개발용: 1444년 훈민정음 반대 상소 장면의 최만리·세종 인터뷰 3묶음", "data/eval/v3_20260929_다회차_훈민정음.json"],
                ["처음 보는 질문", "24 × 2", "검증용: 개발에 쓰지 않은 한능검 문항. 같은 사실을 용어 있는 말 / 쉬운 말로. 잠근 뒤 실행, 재료 절반은 봉인", "data/eval/holdout_v1(b)_20260930.jsonl"],
                ["새 사건 대화(계유정난)", "20턴", "검증용: 개발에 안 쓴 사건. ChatGPT와 같은 질문으로 비교", "data/eval/v4_20261001_다회차_계유정난.json"]]
    fact = [["번호", "유형", "주제", "질문", "정답(기대 답)", "근거 위치", "한능검 출처(회차·문항)"]]
    for q in _jsonl("v3_20260929_한능검코퍼스+함정보강.jsonl"):
        fact.append([q["id"], q["category"], q.get("topic", ""), q["question"], q["expected"],
                     _where(q.get("gold_chunks", []), chunks), ", ".join(q.get("hanneung", []))])
    hold = [["번호", "유형", "주제", "질문(용어 있는 말)", "질문(쉬운 말)", "정답(기대 답)", "근거 위치"]]
    easy = {q["id"]: q for q in _jsonl("holdout_v1b_20260930.jsonl")}
    for q in _jsonl("holdout_v1_20260930.jsonl"):
        hold.append([q["id"], q["category"], q.get("topic", ""), q["question"], easy[q["id"]]["question"],
                     q["expected"], _where(q.get("gold_chunks", []), chunks)])
    sheets = [("개요", overview, "평가셋 4묶음. 문항마다 정답과 근거 위치(어느 기사의 몇 번째 청크)를 적었다"),
              ("사실 질문 67", fact, "개발용. 함정(틀린 전제·다른 시대), 자료 없음, 일부만 있음 문항 포함")]
    for title, fname, sids in (("인물 대화 30턴", "v3_20260929_다회차_훈민정음.json", "ABC"),
                               ("새 사건 대화 20턴", "v4_20261001_다회차_계유정난.json", "DE")):
        data = json.load(open(EVAL / fname, encoding="utf-8"))
        rows = [["묶음", "장면 설정", "번호", "확인할 것", "질문", "통과 기준", "근거 위치"]]
        for sid in sids:
            sc = data[sid]
            for i, t in enumerate(sc["turns"]):
                rows.append([f"{sid} {sc['title']}", sc["setup"] if i == 0 else "", t["id"], t.get("check", ""),
                             t["user"], t.get("pass_rule", ""), _where(t.get("gold_chunks", []), chunks)
                             if t.get("gold_chunks") else ""])
        sheets.append((title, rows, "턴마다 질문과 통과 기준. 장면 이후 일을 말하면 '누설'로 실패"))
    sheets.insert(2, ("처음 보는 질문 24", hold, "검증용. 같은 사실을 두 가지 말로 물음(검색이 실록 용어에만 기대는지 확인)"))
    return sheets


EVIDENCE_CSV = ROOT / "results" / "20261002_근거보기_표시4종" / "표시채점_표본50턴_20261002.csv"
SET_FILE = {"v3": "v3_20260929_한능검코퍼스+함정보강.jsonl", "holdout_v1_20260930": "holdout_v1_20260930.jsonl",
            "holdout_v1b_20260930": "holdout_v1b_20260930.jsonl"}


def grade_sheets():
    gold = {(s, q["id"]): q.get("gold_chunks", []) for s, f in SET_FILE.items() for q in _jsonl(f)}
    head = ["묶음", "실행", "번호", "유형", "질문", "챗봇 답", "판정", "판정(세부)", "판정 이유",
            "정답 근거 적중(최종 4개)", "LLM 채점기 판정(gpt-4o-mini)", "LLM 채점기와 일치"]
    rows = [head]
    for r in csv.DictReader(open(GRADE_CSV, encoding="utf-8-sig")):
        if r["set"] in SET_NAME:
            g = gold.get((r["set"], r["qid"]), [])
            hit = ("O" if set(ast.literal_eval(r["new_context"])) & set(g) else "X") if g else ""
            llm = THREE.get(r["new_verdict"], r["new_verdict"])
            rows.append([SET_NAME[r["set"]], "1회", r["qid"], r["category"], r["question"], r["new_answer"],
                         THREE.get(r["new_review"], r["new_review"]), r["new_review"], r["review_reason"], hit,
                         r["new_verdict"], "O" if llm == THREE.get(r["new_review"]) else "X"])
    role_gold = {t["id"]: t.get("gold_chunks", []) for sid, sc in
                 json.load(open(EVAL / "v4_20261001_다회차_계유정난.json", encoding="utf-8")).items() for t in sc["turns"]}
    for group, (folder, sids) in ROLE_RUNS.items():
        for sid in sids:
            files = sorted((ROOT / "results" / folder).glob(f"*_scenario{sid}_*.human.csv"))
            for run, human in enumerate(files, 1):
                answers = {d["qid"]: d for d in map(json.loads, open(str(human).replace(".human.csv", ".jsonl"),
                                                                       encoding="utf-8")) if d.get("qid")}
                for h in csv.DictReader(open(human, encoding="utf-8-sig")):
                    d = answers.get(h["qid"], {})
                    g = role_gold.get(h["qid"], []) if sid in "DE" else []
                    hit = ("O" if set(d.get("context_ids", [])) & set(g) else "X") if g else ""
                    rows.append([group, f"{run}회", h["qid"], d.get("check") or "", d.get("question", ""),
                                 d.get("answer", ""), THREE.get(h["판정"], h["판정"]), h["판정"], h["메모"], hit, "", ""])
    n = len(rows)
    A, G, H, D, J, L = (f"'전체 채점'!${c}$4:${c}${n + 2}" for c in "AGHDJL")
    groups = ["사실 질문", "처음 보는 질문(용어 있는 말)", "처음 보는 질문(쉬운 말)", "인물 대화(훈민정음)", "새 사건 대화(계유정난)"]
    over = [["묶음", "채점한 답 수", "정답", "부분", "오답", "정답 비율"]]
    for i, g in enumerate(groups, 4):
        over.append([g, f"=COUNTIF({A},A{i})", f'=COUNTIFS({A},A{i},{G},"정답")', f'=COUNTIFS({A},A{i},{G},"부분")',
                     f'=COUNTIFS({A},A{i},{G},"오답")', f"=IF(B{i}=0,0,ROUND(C{i}/B{i}*100,1))"])

    ev = list(csv.DictReader(open(EVIDENCE_CSV, encoding="utf-8-sig")))
    ev_ok = sum(e["판정"] == "맞음" for e in ev)
    rec = [e for e in ev if e["표시"] == "기록"]
    rec_ok = len(rec) - sum(e["오류 유형"] == "근거 부적합" for e in rec)
    pct = lambda a, b: f'=TEXT({a},"0")&" / "&TEXT({b},"0")&" ("&TEXT(IF({b}=0,0,{a}/{b}*100),"0")&"%)"'
    # 행은 묶음, 열은 로드맵 채점 기준(사용자 2026-10-02). 해당 없는 칸은 "-". 기준 설명은 표 아래에 따로.
    cols = ["묶음", "검색 적중률", "답 정확도", "근거 표시 정확도", "없는 질문 처리", "LLM 채점기 일치(gpt-4o-mini ↔ Claude)", "사람 채점 일치(Claude ↔ 사람)"]
    crit = [cols]
    for g in groups:
        f = lambda col, val: f'COUNTIFS({A},"{g}",{col},"{val}")'
        hit = pct(f(J, "O"), f"({f(J, 'O')}+{f(J, 'X')})") if g != "인물 대화(훈민정음)" else "-"
        acc = pct(f(G, "정답"), f'COUNTIF({A},"{g}")')
        na_all = f'COUNTIFS({A},"{g}",{D},"자료 없음*")'
        na = pct(f'COUNTIFS({A},"{g}",{D},"자료 없음*",{H},"적절한 보류")', na_all) if g in SET_NAME.values() else "-"
        llm = pct(f(L, "O"), f"({f(L, 'O')}+{f(L, 'X')})") if g in SET_NAME.values() else "-"
        crit.append([g, hit, acc, "-", na, llm, "-"])
    crit.append(["근거 보기 표본(인물 대화 50턴)", "-", "-",
                 f"{ev_ok} / {len(ev)} ({ev_ok / len(ev) * 100:.0f}%) · 근거 기사 {rec_ok} / {len(rec)}", "-", "-", "-"])
    crit.append(["사람 채점 표본(30개)", "-", "-", "-", "-", "-",
                 pct("COUNTIF('LLM과 사람 채점 비교'!$E$4:$E$33,\"O\")", "30")])
    crit += [[], ["채점 기준", "무엇을 쟀나"],
             ["검색 적중률", "정답 청크가 답변에 들어간 최종 4개(리랭커가 고른 것) 안에 있었나. 정답 청크를 정한 문항만(훈민정음 대화는 정하지 않아 '-')"],
             ["답 정확도", "Claude 채점에서 정답인 답의 비율. '적절한 보류'는 정답, '부적절한 보류'(자료에 있는데 없다고 함)는 오답으로 셈"],
             ["근거 표시 정확도", "답 문장마다 붙인 실록 기록 / 실록 풀이 / 인물 시점 / AI 창작 표시가 맞나(Claude 채점 + 사람 검수). 아래 줄은 '실록 기록'에 붙인 근거 기사가 그 문장을 뒷받침하는 비율"],
             ["없는 질문 처리", "자료에 없는 질문(자료 없음 문항)에 지어내지 않고 '자료에 없다'고 한 비율"],
             ["LLM 채점기 일치", "LLM 자동 채점기(gpt-4o-mini, `llm-grade`)와 Claude 검수의 정답/부분/오답이 같은 비율"],
             ["사람 채점 일치", "Claude 판정을 가리고 사람이 채점한 결과와 Claude 판정이 같은 비율(2026-10-02)"],
             ["실행", "모두 2026-10-01 실행(사실·역할 규칙 v8로 바꾸기 전). 근거는 '전체 채점'·'LLM과 사람 채점 비교' 시트"]]

    cmp_rows = [["번호", "묶음", "Claude 판정", "사람 판정", "가린 채 일치", "합의 판정", "합의 근거", "Claude 이유", "사람 메모"]]
    for r in csv.DictReader(open(HUMAN_CMP, encoding="utf-8-sig")):
        cmp_rows.append([r["qid"], r["묶음"], r["Claude(3단계)"], r["사람 판정"], r["일치"], r["합의 판정"],
                         r["합의 근거"], r["Claude 이유"], r["사람 메모"]])
    return [("채점 기준별 결과", crit, "로드맵 4단계 채점 기준을 묶음별로. 결과는 다른 시트를 세는 수식(근거 표시만 별도 파일 값). 각 기준의 뜻은 표 아래"),
            ("개요", over, "묶음별 정답/부분/오답 수(전체 채점 시트를 세는 수식, 정답 비율은 %). 판정은 Claude, 판정(세부)의 '적절한 보류'는 정답·'부적절한 보류'는 오답으로 셈"),
            ("전체 채점", rows, "2026-10-01 실행(규칙 v8로 바꾸기 전). 인물 대화·새 사건은 2회씩 돌린 것을 모두 실음. 판정은 Claude. 정답 근거 적중은 정답 청크가 정해진 문항만(훈민정음 대화는 없음)"),
            ("LLM과 사람 채점 비교", cmp_rows, "표본 30개를 Claude 판정을 가린 채 사람이 채점: 처음 일치 19/30(63%). 어긋난 문항으로 채점 기준을 합의(2026-10-02)")]
