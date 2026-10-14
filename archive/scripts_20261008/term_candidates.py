"""용어 점검 1단계: 우리 번역문에서 괄호 한자가 붙은 낱말(예: 성역(城役))을 모두 뽑아 센다(작업기록 [208]).

AI 초안 번역은 어려운 한자어를 괄호 한자와 함께 그대로 두는 경향이 있다. 일반 사용자가 모를 말을 고르기 위한 후보 목록이다.
- 청크의 원문 표시(persons·places·books)와 한자가 겹치면 인명·지명·서명으로 먼저 나눈다. 나머지는 '용어 후보'다.
  원문 표시는 빠진 것이 많아 이 구분은 대략이다. 최종 분류(풀어 쓸 말 / 주석만 / 그대로)는 사람이 정한다.
- 비용 없음(파일만 읽음). 출력은 docs/기록/데이터가공/용어점검_후보_<날짜>.csv

실행: python scripts/term_candidates.py
"""
import collections
import csv
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sillok_rag.corpus import load_chunks  # noqa: E402

HAN = r"[㐀-䶿一-鿿豈-﫿]"
TERM = re.compile(rf"([가-힣]+)\(({HAN}[^()]*?)\)")
OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "기록" / "데이터가공"


def kind(han: str, chunk: dict) -> str:
    """원문 표시와 한자가 겹치면 인명·지명·서명. 이름 일부만 표시된 경우(崔萬理 ↔ 萬理)도 겹침으로 본다."""
    core = re.sub(r"[^㐀-䶿一-鿿豈-﫿]", "", han)
    for label, tags in (("서명", chunk.get("books") or []), ("인명", chunk.get("persons") or []),
                        ("지명", chunk.get("places") or [])):
        if any(len(t) >= 2 and (t in core or core in t) for t in tags):
            return label
    return "용어 후보"


def main():
    rows: dict[tuple, dict] = {}
    for c in load_chunks():
        for m in TERM.finditer(c["translation"]):
            word, han = m.group(1), m.group(2)
            r = rows.setdefault((word, han), {"낱말": word, "한자": han, "출현": 0, "청크": set(),
                                               "종류": collections.Counter(), "예 청크": c["chunk_id"],
                                               "예 문맥": c["translation"][max(0, m.start() - 30):m.end() + 30]})
            r["출현"] += 1
            r["청크"].add(c["chunk_id"])
            r["종류"][kind(han, c)] += 1
    out = sorted(rows.values(), key=lambda r: (-len(r["청크"]), r["낱말"]))
    path = OUT_DIR / f"용어점검_후보_{date.today():%Y%m%d}.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["낱말", "한자", "종류(대략)", "출현", "청크 수", "예 청크", "예 문맥"])
        for r in out:
            w.writerow([r["낱말"], r["한자"], r["종류"].most_common(1)[0][0], r["출현"], len(r["청크"]),
                        r["예 청크"], r["예 문맥"].replace("\n", " ")])
    kinds = collections.Counter(r["종류"].most_common(1)[0][0] for r in out)
    print(f"괄호 한자 낱말 {len(out)}개(출현 {sum(r['출현'] for r in out)}번): {dict(kinds)}")
    print(path)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
