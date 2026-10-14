"""청크를 다시 나눈 뒤(규칙서 v2) 예전 청크의 번역·메타데이터를 새 청크로 옮긴다 (2026-09-30).

사용법:
    python scripts/migrate_translations.py 비교           # 예전 ↔ 새 청크 대응만 보여 준다
    python scripts/migrate_translations.py 옮기기 <나눔번역.json>   # data/번역/*.jsonl을 새 청크 ID로 다시 쓴다

원문(공백 무시)으로 짝을 찾는다.
    같음   : 새 청크 원문 = 예전 청크 하나 → 번역·화자·시점·note 그대로, ID만 바꿈
    합침   : 새 청크 원문 = 예전 청크 여러 개를 이은 것 → 번역을 이어 붙임(화자·시점은 확인 필요 표시)
    나눔   : 새 청크가 예전 청크의 일부 → 번역을 사람이(메인 세션이) 나눠 써야 함. MANUAL_SPLIT에 적는다
평가셋 정답 청크 ID를 바꿀 때 쓰는 예전 → 새 ID 대응표도 data/청크/청크대응_{새 태그}.csv로 낸다.

주의: '예전 청크'로 data/corpus.jsonl(v1b)을 읽으므로 **v2로 옮긴 뒤에는 다시 실행하지 않는다**.
2026-09-30에 커밋 0f3b63f의 코퍼스(793청크)를 기준으로 한 번 실행했다(규칙서 10장, 작업기록 [120]).
나눔·합침 55청크의 번역(JSON)은 메인 세션이 예전 번역을 문장 단위로 나눠 쓴 것이고, 결과는 data/번역/에 들어 있다.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "data" / "corpus.jsonl"                                  # 예전 청크 + 번역(v1b)
NEW = ROOT / "data" / "청크" / "청크초안_20260930_v2.jsonl"
TRANS_DIR = ROOT / "data" / "번역"
MAP_OUT = ROOT / "data" / "청크" / "청크대응_20260930_v2.csv"


def norm(s: str) -> str:
    """공백과 따옴표를 뺀 원문(v2에서 닫는 따옴표가 옆 청크로 옮겨진 것은 같은 청크로 본다).
    v2에서 지운 권 끝 표시(…實錄卷第…)도 뺀다."""
    s = re.sub(r"\S{2,8}(?:實錄|日記)卷第[一二三四五六七八九十百]+終?$", "", s.strip())
    return re.sub(r"[\s\"“”‘’「」]", "", s)


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def match() -> list[dict]:
    """새 청크마다 {new, kind, old: [예전 청크 ID…]}."""
    old = read_jsonl(OLD)
    new = read_jsonl(NEW)
    by_art_old: dict[str, list[dict]] = {}
    for c in old:
        by_art_old.setdefault(c["article_id"], []).append(c)
    rows = []
    for n in new:
        olds = by_art_old[n["article_id"]]
        text = norm(n["original"])
        exact = [o for o in olds if norm(o["original"]) == text]
        if exact:
            rows.append({"new": n, "kind": "같음", "old": [exact[0]["chunk_id"]]})
            continue
        # 연속한 예전 청크들을 이은 것과 같은가
        joined = None
        for i in range(len(olds)):
            acc = ""
            for j in range(i, len(olds)):
                acc += norm(olds[j]["original"])
                if acc == text:
                    joined = [o["chunk_id"] for o in olds[i:j + 1]]
                    break
                if not text.startswith(acc):
                    break
            if joined:
                break
        if joined:
            rows.append({"new": n, "kind": "합침", "old": joined})
            continue
        # 일부만 겹침: 새 원문과 글자가 겹치는 예전 청크들
        over = [o["chunk_id"] for o in olds if norm(o["original"]) in text or text in norm(o["original"])
                or _overlap(norm(o["original"]), text) >= 8]
        rows.append({"new": n, "kind": "나눔", "old": over})
    return rows


def _overlap(a: str, b: str) -> int:
    """a의 끝과 b의 앞(또는 그 반대)이 겹치는 글자 수."""
    best = 0
    for k in range(min(len(a), len(b)), 7, -1):
        if a.endswith(b[:k]) or b.endswith(a[:k]):
            best = k
            break
    return best


def show(rows: list[dict]) -> None:
    from collections import Counter
    print(Counter(r["kind"] for r in rows))
    for r in rows:
        if r["kind"] != "같음":
            print(f"{r['kind']} {r['new']['chunk_id']} ← {r['old']} | {r['new']['original'][:70]}")


FIELDS = ("speaker", "quoted", "event_date", "known_from", "translation", "note")


def migrate(rows: list[dict], split_path: Path) -> None:
    """번역 파일을 새 청크 ID로 다시 쓴다. 같음은 그대로, 나눔·합침은 split_path(JSON: 새 ID → 칸)에서 가져온다."""
    split = json.loads(split_path.read_text(encoding="utf-8"))
    old_trans: dict[str, dict] = {}
    file_of_article: dict[str, str] = {}
    for p in sorted(TRANS_DIR.glob("*.jsonl")):
        for t in read_jsonl(p):
            old_trans[t["chunk_id"]] = t
            file_of_article.setdefault(t["chunk_id"].rsplit("-", 1)[0], p.name)
    out: dict[str, list[dict]] = {}
    missing = []
    for r in rows:
        nid = r["new"]["chunk_id"]
        if r["kind"] == "같음":
            src = old_trans[r["old"][0]]
            t = {"chunk_id": nid, **{k: src[k] for k in FIELDS}}
        elif nid in split:
            t = {"chunk_id": nid, **{k: split[nid][k] for k in FIELDS}}
        else:
            missing.append(nid)
            continue
        out.setdefault(file_of_article[r["new"]["article_id"]], []).append(t)
    unused = set(split) - {r["new"]["chunk_id"] for r in rows if r["kind"] != "같음"}
    if missing or unused:
        raise SystemExit(f"번역이 없는 새 청크: {missing} / 쓰이지 않은 나눔 번역: {sorted(unused)}")
    for name, ts in out.items():
        with open(TRANS_DIR / name, "w", encoding="utf-8", newline="\n") as f:
            for t in ts:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    # 예전 ID → 새 ID 대응표 (평가셋 정답 청크 다시 매기기용)
    back: dict[str, list[str]] = {}
    for r in rows:
        for o in r["old"]:
            back.setdefault(o, []).append(r["new"]["chunk_id"])
    with open(MAP_OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["예전_chunk_id", "새_chunk_id", "관계"])
        for o in sorted(back):
            kinds = {r["kind"] for r in rows if o in r["old"]}
            w.writerow([o, "|".join(back[o]), "/".join(sorted(kinds))])
    print(f"번역 파일 {len(out)}개 다시 씀, 새 청크 {sum(len(v) for v in out.values())}개. 대응표: {MAP_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "비교"
    rows = match()
    if cmd == "비교":
        show(rows)
    elif cmd == "옮기기" and len(sys.argv) > 2:
        migrate(rows, Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
