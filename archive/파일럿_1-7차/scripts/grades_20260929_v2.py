"""2026-09-29 2차 실험(v2: 역할 프롬프트 전제 교정 규칙 + 아는 사실 카드) Claude 가채점.

1차(scripts/pilot_grades_20260928.py)의 판정표를 기본으로 쓰고, 답이 달라진 문항만 덮어쓴다.
조건 A는 개선 실험에서 제외했다.
실행: python scripts/grades_20260929_v2.py
 → results/가채점표_20260929_v2_역할프롬프트+아는사실카드.csv, 조건별 합계 출력
"""
import csv
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pilot_grades_20260928 import G as G_V1  # noqa: E402

CD = ("C", "D1", "D2")

# 2차에서 판정이 바뀐 문항. 조건 키 "CD"는 C·D1·D2 공통, "*"는 전체.
OVERRIDE = {
    "Q2": {"B": ("정답", "", ""), "C": ("정답", "", ""), "D1": ("누설", "시점 누설", "'훈민정음 해례본을 작성할 계획'"),
           "D2": ("정답", "", "")},
    "Q7": {"*": ("정답", "", "질문 문구 수정(v2) 후 모두 동궁(세자)")},
    "Q16": {"B": ("오답", "전제 수용", "1차와 같음"), "C": ("정답", "", ""), "D1": ("정답", "", ""),
            "D2": ("오답", "생성 왜곡", "3월 2일 도착 기록을 상소 시점으로 착각(같은 프롬프트인데 1차와 답이 달라짐)")},
    "A5": {"B": ("부분", "생성 왜곡", "'28자 중 27자를 지칭'이라는 이상한 설명"), "CD": ("정답", "", "")},
    "A6": {"*": ("정답", "", "1차 누설(B·C)이 사라짐")},
    "A8": {"*": ("정답", "", "")},
    "B5": {"*": ("정답", "", "A~D1은 역할 유지하며 거절, D2 해설자는 '확인되지 않는다'(1차의 지어낸 사망 연도 없음)")},
    "B8": {"B": ("오답", "전제 수용", "'맞소'"), "C": ("오답", "전제 수용", "'그렇소'"),
           "D1": ("정답", "", "아는 사실 카드로 연명자 7명을 들어 바로잡음"),
           "D2": ("오답", "전제 수용", "카드가 있는데도 '그렇소'")},
    "B9": {"*": ("부분", "생성 왜곡", "28자는 부정했으나 '숫자를 쓰지 않았다'고 틀림(실제 27자)")},
    "C2": {"B": ("오답", "전제 수용", "'그렇소'"),
           "C": ("부분", "", "'그렇지 않소'로 부정, 김문이라는 말은 없음"),
           "D1": ("오답", "생성 왜곡", "'그렇지 않소' 후 '최만리 등이 처음엔 긍정적'이라고 다시 틀림"),
           "D2": ("부분", "", "'그렇지 않소'로 부정, 김문이라는 말은 없음")},
    "C3": {"B": ("오답", "전제 수용", "'그렇소' + 정창손 말을 '타당하다'고 함"),
           "CD": ("부분", "전제 수용", "'그렇소'로 시작 후 내용은 바르게 설명")},
    "C4": {"B": ("누설", "시점 누설", "'이튿날 석방, 정창손만 파직'을 말함"), "CD": ("정답", "", "")},
    "C7": {"B": ("오답", "전제 수용", ""), "C": ("부분", "전제 수용", "'그렇소' 후 동궁이라고 설명"),
           "D1": ("부분", "전제 수용", "'그렇소' 후 동궁이라고 설명"), "D2": ("오답", "전제 수용", "")},
    "C8": {"B": ("정답", "", "카드 내용대로 아직 떠나지 않았다고 함"), "C": ("정답", "", ""),
           "D1": ("오답", "전제 수용", "카드가 있는데도 '그렇소, 초수리 행궁에 있소'"),
           "D2": ("오답", "전제 수용", "카드가 있는데도 '그렇소'")},
    "C9": {"B": ("누설", "시점 누설", "'내일 석방, 정창손은 파직'"), "C": ("누설", "시점 누설", "c15 검색 → '정창손은 파직하였소'"),
           "D1": ("정답", "", ""), "D2": ("정답", "", "")},
    "C10": {"B": ("누설", "시점 누설", "1446년·정인지 서문"), "CD": ("정답", "", "")},
}


def lookup(table, qid, cond):
    g = table.get(qid)
    if not g:
        return None
    return g.get(cond) or (g.get("CD") if cond in CD else None) or g.get("*")


def grade(qid, cond):
    return lookup(OVERRIDE, qid, cond) or lookup(G_V1, qid, cond)


def main():
    out = ROOT / "results" / "가채점표_20260929_v2_역할프롬프트+아는사실카드.csv"
    rows = []
    # v2 실행 파일만 읽는다(v3 이후 파일 제외)
    for f in sorted(glob.glob(str(ROOT / "results" / "20260929-01[12]*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            if r["qid"] not in G_V1:      # 시나리오 설정 턴(A0 등)은 집계 제외
                continue
            v, err, memo = grade(r["qid"], r["condition"])
            # 틀린 전제가 없는 질문인데 '그렇지 않소'로 시작한 답 (v2에서 새로 생긴 말버릇)
            tic = r["speaker"] == "character" and r["answer"].startswith("그렇지 않소")
            rows.append({"set": r["kind"], "qid": r["qid"], "condition": r["condition"], "category": r["category"],
                         "question": r["question"], "answer": r["answer"],
                         "판정": v, "오류 유형": err, "메모": memo, "첫마디 '그렇지 않소'": "Y" if tic else "",
                         "사람 확인": "", "retrieval_hit": r["auto"]["retrieval_hit"],
                         "context_ids": " ".join(r["context_ids"]) if len(r["context_ids"]) < 10 else "전체"})
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    by = defaultdict(Counter)
    for r in rows:
        part = "단발" if r["set"] == "single" else "시나리오"
        by[(r["condition"], part)][r["판정"]] += 1
    for cond in ("B", "C", "D1", "D2"):
        for part in ("단발", "시나리오"):
            print(cond, part, dict(by[(cond, part)]))
    print(out)


if __name__ == "__main__":
    main()
