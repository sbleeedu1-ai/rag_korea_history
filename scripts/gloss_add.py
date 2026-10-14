"""청크별 쉬운 말 풀이(용어 주석)를 번역 파일(data/번역/*.jsonl)의 gloss 칸에 넣는다(작업기록 [233]).

강사 피드백(중간점검 8번 막힌 부분): 청크 안에 쉬운 말 풀이를 달아 검색에도 쓰고, 화면에서는 용어를 누르면 풀이가 뜨게 한다.
풀이는 번역문에 붙은 정보라 번역 파일에 함께 두고, build_corpus.py가 corpus.jsonl로 옮긴다.

입력 파일 한 줄 = 청크 하나:  청크ID<TAB 또는 " | ">용어=풀이 ; 용어=풀이 ; ...
- 용어는 그 청크의 번역문에 실제로 있는 글자 그대로여야 한다(화면에서 밑줄을 긋기 위해). 없으면 멈추고 알린다.
- 같은 청크를 다시 넣으면 그 청크의 풀이를 새것으로 바꾼다.

사용법: python scripts/gloss_add.py <입력 파일>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANS_DIR = ROOT / "data" / "번역"


def parse(path: Path) -> dict[str, list[dict]]:
    rows = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        cid, _, body = line.partition("\t") if "\t" in line else line.partition(" | ")
        items = []
        for part in body.split(" ; "):
            term, sep, gloss = part.partition("=")
            if not sep or not term.strip() or not gloss.strip():
                sys.exit(f"{path.name} {n}줄: '용어=풀이' 형식이 아님: {part!r}")
            if len(term.strip()) < 2:  # 한 글자는 화면에서 다른 낱말("결정"의 결)에도 밑줄이 그어짐 → "1결"처럼 문맥을 붙임
                sys.exit(f"{path.name} {n}줄: 한 글자 용어는 문맥을 붙여 쓰기: {part!r}")
            items.append({"용어": term.strip(), "풀이": gloss.strip()})
        rows[cid.strip()] = items
    return rows


def main() -> None:
    new = parse(Path(sys.argv[1]))
    files = {p: [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
             for p in sorted(TRANS_DIR.glob("*.jsonl"))}
    trans = {t["chunk_id"]: t["translation"] for rows in files.values() for t in rows}
    bad = [(cid, g["용어"]) for cid, items in new.items() for g in items
           if cid not in trans or g["용어"] not in trans[cid]]
    if bad:
        for cid, term in bad:
            print(f"번역문에 없음: {cid} {term}")
        sys.exit(1)
    for p, rows in files.items():
        if not any(t["chunk_id"] in new for t in rows):
            continue
        for t in rows:
            if t["chunk_id"] in new:
                t["gloss"] = new[t["chunk_id"]]
        p.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in rows), encoding="utf-8", newline="\n")
    done = [t for rows in files.values() for t in rows if t.get("gloss")]
    print(f"더함 {len(new)}청크 · 지금 {len(done)}청크 · 용어 {sum(len(t['gloss']) for t in done)}개")


if __name__ == "__main__":
    main()
