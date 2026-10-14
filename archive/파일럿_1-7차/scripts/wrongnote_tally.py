"""오답노트 집계표: 실험별 가채점표에서 틀린·부분·누설·부적절한 보류 행을 실패 유형별로 센다.

세부 오류 유형 → 과정 5단계 분류(검색 실패 / 생성 왜곡 / 문서에 없음 / 질문 모호)
실행: python scripts/wrongnote_tally.py   (새 실험 채점표가 생기면 SHEETS에 한 줄 추가)
"""
import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHEETS = [
    ("1차 파일럿(v1)", ROOT / "results" / "pilot_20260928_grades.csv"),
    ("2차(v2) 역할프롬프트+카드", ROOT / "results" / "가채점표_20260929_v2_역할프롬프트+아는사실카드.csv"),
    ("3차(v3) 말투 수정, top_k 4", ROOT / "results" / "가채점표_20260929_v3_말투수정_k4.csv"),
    ("3차(v3) 말투 수정, top_k 8", ROOT / "results" / "가채점표_20260929_v3_말투수정+top_k8.csv"),
    ("4차 하이브리드 검색", ROOT / "results" / "가채점표_20260929_v4_하이브리드검색.csv"),
    ("4차 비교용 BM25만", ROOT / "results" / "가채점표_20260929_v4_BM25만.csv"),
    ("5차 사실 규칙 v4(과잉 보류)", ROOT / "results" / "가채점표_20260929_v5_사실규칙v4_과잉보류.csv"),
    ("6차 카드를 대화 첫 턴에(전제 교정)", ROOT / "results" / "가채점표_20260929_v6_카드첫턴_전제교정.csv"),
    ("7차 사전 판정 + 중립 검색어", ROOT / "results" / "가채점표_20260929_v7_사전판정+중립검색어.csv"),
]
FAIL = {"오답", "부분", "누설", "부적절한 보류"}
BIG = {
    "검색 실패": "검색 실패",
    "질문 모호": "질문 모호",
    "문서에 없음": "문서에 없음",
    "전제 수용": "생성 왜곡",
    "시점 누설": "생성 왜곡",
    "과잉 보류": "생성 왜곡",
    "기타 왜곡": "생성 왜곡",
    "누락·불완전": "생성 왜곡",
    "한문 오독": "생성 왜곡",
}
BIG_ORDER = ["검색 실패", "생성 왜곡", "문서에 없음", "질문 모호"]
SUB_ORDER = ["전제 수용", "시점 누설", "과잉 보류", "기타 왜곡", "한문 오독", "누락·불완전"]


def main():
    for name, path in SHEETS:
        rows = [r for r in csv.DictReader(open(path, encoding="utf-8-sig")) if r["판정"] in FAIL]
        conds = sorted({r["condition"] for r in rows}, key=["A", "B", "C", "D1", "D2"].index)
        big, sub = defaultdict(Counter), defaultdict(Counter)
        for r in rows:
            s = r["오류 유형"] or "누락·불완전"   # 유형을 안 적은 부분 정답 = 일부만 답함
            if s == "생성 왜곡":
                s = "기타 왜곡"
            sub[s][r["condition"]] += 1
            big[BIG.get(s, "생성 왜곡")][r["condition"]] += 1
        print(f"\n### {name} (실패 행 {len(rows)}개)\n")
        print("| 분류 | 세부 | " + " | ".join(conds) + " | 합 |")
        print("|---|---|" + "---|" * (len(conds) + 1))
        for b in BIG_ORDER:
            print(f"| **{b}** | | " + " | ".join(str(big[b][c]) for c in conds) + f" | **{sum(big[b].values())}** |")
            for s in SUB_ORDER:
                if sub[s] and BIG.get(s, "생성 왜곡") == b and s != b:
                    print(f"| | {s} | " + " | ".join(str(sub[s][c]) for c in conds) + f" | {sum(sub[s].values())} |")


if __name__ == "__main__":
    main()
