"""이미 넣은 쉬운 말 풀이(gloss)를 용어 단위로 고치거나 뺀다(작업기록 [238]).

gloss_add.py는 청크 하나의 풀이를 통째로 바꾸므로, 사전 확인처럼 용어 몇 개만 고칠 때는 이 도구를 쓴다.

입력 파일 한 줄:  용어<TAB>청크ID 또는 *<TAB>새 풀이[<TAB>새 용어]
- 청크ID가 *이면 그 용어가 나오는 모든 청크를 고친다.
- 청크ID 자리에 =이전 풀이 를 쓰면 그 풀이가 붙은 청크만 고친다(한 용어에 풀이가 여럿일 때).
- 새 풀이가 비어 있으면 그 청크에서 그 용어의 풀이를 뺀다.
- 넷째 칸에 새 용어를 쓰면 용어 이름도 바꾼다(예: '공부(貢賦)' → '공부', 작업기록 [242]).
- 고칠 대상이 하나도 없는 줄이 있으면 멈추고 알린다(오타 방지).

사용법: python scripts/gloss_fix.py <입력 파일>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANS_DIR = ROOT / "data" / "번역"


def parse(path: Path) -> list[tuple[str, str, str, str]]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            sys.exit(f"{path.name} {n}줄: '용어<TAB>청크ID<TAB>새 풀이' 형식이 아님: {line!r}")
        term, cid = parts[0].strip(), parts[1].strip()
        gloss = parts[2].strip() if len(parts) > 2 else ""
        new_term = parts[3].strip() if len(parts) > 3 else ""
        if new_term and not gloss:
            sys.exit(f"{path.name} {n}줄: 용어 이름을 바꿀 때는 새 풀이도 써야 함: {line!r}")
        rows.append((term, cid, gloss, new_term or term))
    return rows


def main() -> None:
    fixes = parse(Path(sys.argv[1]))
    files = {p: [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
             for p in sorted(TRANS_DIR.glob("*.jsonl"))}
    hit = {i: 0 for i in range(len(fixes))}
    changed = set()
    for p, rows in files.items():
        for t in rows:
            if not t.get("gloss"):
                continue
            kept = []
            for g in t["gloss"]:
                for i, (term, cid, gloss, new_term) in enumerate(fixes):
                    if g["용어"] == term and (cid in ("*", t["chunk_id"]) or cid == "=" + g["풀이"]):
                        hit[i] += 1
                        changed.add(p)
                        if not gloss:
                            g = None
                        else:
                            g = {"용어": new_term, "풀이": gloss}
                        break
                if g is not None:
                    kept.append(g)
            if kept:
                t["gloss"] = kept
            else:
                t.pop("gloss")
    missing = [fixes[i] for i, n in hit.items() if n == 0]
    if missing:
        for term, cid, *_ in missing:
            print(f"고칠 대상 없음: {term} {cid}")
        sys.exit(1)
    for p in changed:
        p.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in files[p]), encoding="utf-8", newline="\n")
    print(f"고친 줄 {len(fixes)}개 · 바뀐 풀이 {sum(hit.values())}곳 · 파일 {len(changed)}개")


if __name__ == "__main__":
    main()
