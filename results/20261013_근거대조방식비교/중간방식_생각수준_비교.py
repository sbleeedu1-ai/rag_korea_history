"""같은 20턴에서 지금 방식·중간 medium·중간 low·중간 none 비교."""
import json
import statistics
import sys

sys.path.insert(0, r"C:\WORK\rag_korea_history_test")
from ui import episode, episode_gyeyu, runtime
from sillok_rag.evidence import _squash

rows = [r for r in json.load(open(sys.argv[1], encoding="utf-8")) if "mid_none" in r]
GOALS = {**{f"언문-{k}": v for k, v in episode.GOALS.items()}, **{f"계유-{k}": v for k, v in episode_gyeyu.GOALS.items()}}
NAMES = {"old": "지금(medium)", "mid": "중간 medium", "mid_low": "중간 low", "mid_none": "중간 none"}


def goals(r, v):
    return set(runtime.goal_parts({"segments": r[v]["segments"]}, GOALS))


def kept(r, v):
    """지금 방식에서 확인된 기록 문장 가운데 이 방식에서도 기록으로 확인된 수"""
    n = 0
    for s in r["old"]["segments"]:
        if s["label"] == "기록" and s["verified"]:
            q = _squash(s["text"])
            n += any(x["label"] == "기록" and x["verified"] and (_squash(x["text"]) in q or q in _squash(x["text"]))
                     for x in r[v]["segments"])
    return n


rec = sum(1 for r in rows for s in r["old"]["segments"] if s["label"] == "기록" and s["verified"])
print(f"턴 {len(rows)}개, 지금 방식의 확인된 기록 문장 {rec}개\n")
print("| 방식 | 시간 중앙값 | 합계 | 최대 | 생각 토큰 중앙값 | 오류 | 근거 보기 버튼 턴 | 기록 문장 유지 | 목표 항목 합계 | 카드가 지금과 같은 턴 | 목표가 지금과 같은 턴 |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for v in NAMES:
    t = [r[v]["t"] for r in rows]
    print(f"| {NAMES[v]} | {statistics.median(t):.1f}s | {sum(t):.0f}s | {max(t):.1f}s | "
          f"{statistics.median([r[v]['think'] for r in rows]):.0f} | {sum(1 for r in rows if r[v]['error'])} | "
          f"{sum(1 for r in rows if r[v]['cards'])} | {sum(kept(r, v) for r in rows)}/{rec} | "
          f"{sum(len(goals(r, v)) for r in rows)} | {sum(1 for r in rows if set(r[v]['cards']) == set(r['old']['cards']))}/{len(rows)} | "
          f"{sum(1 for r in rows if goals(r, v) == goals(r, 'old'))}/{len(rows)} |")
print("\n턴별 목표 항목(지금 / 중간 medium / low / none):")
for r in rows:
    g = [sorted(goals(r, v)) for v in NAMES]
    if len({tuple(x) for x in g}) > 1:
        print(f"- {r['qid']}: " + " / ".join(str(x) for x in g))
