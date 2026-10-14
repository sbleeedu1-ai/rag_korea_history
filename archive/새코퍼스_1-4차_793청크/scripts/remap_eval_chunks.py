"""청크를 다시 나눈 뒤(규칙서 v2) 평가셋 v3의 청크 참조를 새 청크 ID로 바꾼다 (2026-09-30).

사용법:
    python scripts/remap_eval_chunks.py

- 질문·모범 답·핵심어는 그대로 두고 gold_chunks·near_chunks(단발), known_facts의 source(다회차)만 바꾼다.
- 대응표: data/청크/청크대응_20260930_v2.csv (scripts/migrate_translations.py가 만듦)
- 예전 청크가 둘로 나뉜 곳은 핵심어(must_terms)가 있는 쪽을 사람이 골라 SPLIT_CHOICE에 적는다.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data" / "청크" / "청크대응_20260930_v2.csv"
SINGLE = ROOT / "data" / "eval" / "v3_20260929_한능검코퍼스+함정보강.jsonl"
MULTI = ROOT / "data" / "eval" / "v3_20260929_다회차_훈민정음.json"

# 예전 정답 청크가 둘로 나뉜 문항: 핵심어가 들어 있는 쪽 (2026-09-30 확인)
SPLIT_CHOICE = {
    ("F17", "wnb_12504014_001-04"): ["wnb_12504014_001-04"],   # 부채 글(의리·은혜). 1594년 뒷날 일은 -05
    ("F18", "wna_12506021_004-04"): ["wna_12506021_004-07"],   # 한산도(학익진). 안골포는 -08
    ("F20", "woa_10005007_002-01"): ["woa_10005007_002-02"],   # 이원익 건의(8말·16말). -01은 '설치하였다' 한 문장
}


def load_map() -> dict[str, list[str]]:
    return {r["예전_chunk_id"]: r["새_chunk_id"].split("|") for r in csv.DictReader(open(MAP, encoding="utf-8"))}


def remap(qid: str, ids: list[str], m: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for c in ids:
        new = m[c]
        if len(new) > 1:
            if (qid, c) not in SPLIT_CHOICE:
                raise SystemExit(f"{qid}: {c} 가 {new} 로 나뉨 — SPLIT_CHOICE에 고른 청크를 적으세요")
            new = SPLIT_CHOICE[(qid, c)]
        out += [n for n in new if n not in out]
    return out


def main() -> None:
    m = load_map()
    rows = [json.loads(l) for l in open(SINGLE, encoding="utf-8") if l.strip()]
    changed = 0
    for q in rows:
        for k in ("gold_chunks", "near_chunks"):
            if k in q:
                new = remap(q["id"], q[k], m)
                changed += new != q[k]
                q[k] = new
    raw = SINGLE.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"   # 원래 줄바꿈을 그대로
    if changed:
        with open(SINGLE, "w", encoding="utf-8", newline="") as f:
            for q in rows:
                f.write(json.dumps(q, ensure_ascii=False) + nl)
    sc = json.loads(MULTI.read_text(encoding="utf-8"))
    n_card = 0
    for name, s in sc.items():
        for fact in s.get("known_facts", []):
            new = remap(f"시나리오{name}", [fact["source"]], m)
            if len(new) != 1:
                raise SystemExit(f"시나리오 {name}: {fact['source']} → {new}")
            n_card += new[0] != fact["source"]
            fact["source"] = new[0]
    if n_card:   # 다회차 카드가 바뀔 때만 다시 쓴다(원래 형식: 들여쓰기 2, CRLF, 끝 줄바꿈 없음)
        MULTI.write_bytes(json.dumps(sc, ensure_ascii=False, indent=2).replace("\n", "\r\n").encode("utf-8"))
    print(f"단발 참조 {changed}곳, 다회차 카드 {n_card}곳 바꿈")


if __name__ == "__main__":
    main()
