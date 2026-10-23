"""evidence_fast.json 정리: 지금(old) 방식과 빠른(new)·중간(mid) 방식의 시간·출력, 근거 카드, 문장 표시, 취재 목표 항목(도장)."""
import json
import statistics
import sys

sys.path.insert(0, r"C:\WORK\rag_korea_history_test")
from ui import episode, episode_gyeyu, runtime
from sillok_rag.evidence import _squash

rows = json.load(open(sys.argv[1], encoding="utf-8"))
GOALS = {**{f"언문-{k}": v for k, v in episode.GOALS.items()}, **{f"계유-{k}": v for k, v in episode_gyeyu.GOALS.items()}}
NAMES = {"old": "지금", "new": "빠른(구절은 코드가 찾음)", "mid": "중간(구절은 모델이 고름)"}
variants = [v for v in ("old", "new", "mid") if all(v in r for r in rows)]


def label_of(segments, sentence):
    s = _squash(sentence)
    for seg in segments:
        t = _squash(seg["text"])
        if t and (t in s or s in t):
            return seg["label"] + ("✓" if seg["verified"] else "")
    return "-"


def goals(r, v):
    return set(runtime.goal_parts({"segments": r[v]["segments"]}, GOALS))


print(f"턴 {len(rows)}개\n")
print("| 방식 | 시간 중앙값 | 합계 | 최대 | 출력 토큰 중앙값 | 오류 | 근거 보기 버튼 턴 | 확인된 기록 문장 | 목표 항목 합계 | 카드가 지금과 같은 턴 | 목표가 지금과 같은 턴 |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for v in variants:
    t = [r[v]["t"] for r in rows]
    print(f"| {NAMES[v]} | {statistics.median(t):.1f}s | {sum(t):.0f}s | {max(t):.1f}s | "
          f"{statistics.median([r[v]['out'] for r in rows]):.0f} | {sum(1 for r in rows if r[v]['error'])} | "
          f"{sum(1 for r in rows if r[v]['cards'])} | "
          f"{sum(1 for r in rows for s in r[v]['segments'] if s['label'] == '기록' and s['verified'])} | "
          f"{sum(len(goals(r, v)) for r in rows)} | "
          f"{sum(1 for r in rows if set(r[v]['cards']) == set(r['old']['cards']))}/{len(rows)} | "
          f"{sum(1 for r in rows if goals(r, v) == goals(r, 'old'))}/{len(rows)} |")

for v in variants[1:]:
    rec = [(r, s) for r in rows for s in r["old"]["segments"] if s["label"] == "기록" and s["verified"]]
    kept = sum(1 for r, s in rec if label_of(r[v]["segments"], s["text"]) == "기록✓")
    print(f"\n[{NAMES[v]}] 지금 방식의 확인된 기록 문장 {len(rec)}개 중 같은 문장이 기록으로 확인된 수 {kept}")
    print("목표 항목이 다른 턴:")
    for r in rows:
        a, b = goals(r, "old"), goals(r, v)
        if a != b:
            print(f"- {r['qid']}: 지금 {sorted(a)} / {sorted(b)}")
    print("근거 카드가 다른 턴:")
    for r in rows:
        a, b = set(r["old"]["cards"]), set(r[v]["cards"])
        if a != b:
            print(f"- {r['qid']}: 지금만 {sorted(a - b)} / 이쪽만 {sorted(b - a)}")
