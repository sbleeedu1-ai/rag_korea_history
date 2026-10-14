"""리랭커 none 실행과 10-07 low 3회를 비교한다(API 호출 없음). 검색 적중·전제 판정 메모·누설·걸린 시간."""
import glob
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\sample\rag_korea_history_test\results")
LOW = ["20261007_전제판정나눔", "20261007_전제판정나눔_2회", "20261007_전제판정나눔_3회"]
NONE = "20261013_리랭커none"
SETS = [("단발 개발 67", "_single_D2_"), ("단발 v1 24", "_holdout_v1_2"), ("단발 v1b 24", "_holdout_v1b_"),
        ("대화 A", "_scenarioA_"), ("대화 B", "_scenarioB_"), ("대화 C", "_scenarioC_"),
        ("대화 D", "_scenarioD_"), ("대화 E", "_scenarioE_")]


def load(folder, tag):
    files = sorted(glob.glob(str(ROOT / folder / f"*{tag}*.jsonl")))
    files = [f for f in files if not f.endswith(".llmgrade.jsonl")]
    if not files:
        return None
    return [json.loads(line) for line in open(files[-1], encoding="utf-8")]


def stats(rows):
    hits = [r["auto"].get("retrieval_hit") for r in rows]
    scored = [h for h in hits if h is not None]
    times = [datetime.fromisoformat(r["time"]) for r in rows]
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    return {"n": len(rows), "hit": sum(1 for h in scored if h), "hit_n": len(scored),
            "check": sum(1 for r in rows if r.get("check")),
            "leak": sum(1 for r in rows if r["auto"].get("leak_hits")),
            "fab": sum(1 for r in rows if r["auto"].get("fabricated_quotes")),
            "sec": statistics.median(gaps) if gaps else None}


def key(r):
    return r.get("qid") or f"{r.get('scenario', '')}{r.get('turn', '')}"


lines = []
diffs = []
for label, tag in SETS:
    none = load(NONE, tag)
    lows = [x for x in (load(f, tag) for f in LOW) if x]
    if not none:
        lines.append(f"| {label} | (none 결과 없음) |")
        continue
    s = stats(none)
    ls = [stats(x) for x in lows]
    fmt = lambda st: f"{st['hit']}/{st['hit_n']}"
    lines.append(f"| {label} | {' · '.join(fmt(x) for x in ls)} | {fmt(s)} | "
                 f"{' · '.join(str(x['check']) for x in ls)} | {s['check']} | "
                 f"{' · '.join(str(x['leak']) for x in ls)} | {s['leak']} | "
                 f"{statistics.median([x['sec'] for x in ls]):.1f} | {s['sec']:.1f} |")
    # 문항별: 검색 적중·전제 판정이 low 3회와 다르게 나온 곳
    for r in none:
        k = key(r)
        olds = [next((o for o in x if key(o) == k), None) for x in lows]
        olds = [o for o in olds if o]
        hit_low = [o["auto"].get("retrieval_hit") for o in olds]
        chk_low = [bool(o.get("check")) for o in olds]
        h, c = r["auto"].get("retrieval_hit"), bool(r.get("check"))
        if (h is not None and h not in hit_low) or (c not in chk_low):
            diffs.append(f"- {label} {k}: 적중 low {hit_low} → none {h}, 전제 메모 low {chk_low} → none {c} | {r['question'][:60]}")

print("| 세트 | 검색 적중 low(3회) | none | 전제 메모 수 low | none | 누설 턴 low | none | 문항당 초 low(중앙) | none |")
print("|---|---|---|---|---|---|---|---|---|")
print("\n".join(lines))
print("\n문항별 차이(low 3회 어느 것과도 다른 경우):")
print("\n".join(diffs) or "(없음)")
