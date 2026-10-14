"""화자 라벨 표본 검사용 표본 뽑기(작업기록 [190]).

화자 종류(초안 기준 speaker_kind)별로 층을 나눠 100개를 뽑는다. '기타(확인필요)' 36개는 모두, 나머지는 아래 개수만큼
무작위(시드 고정). 판정은 사람이 원문과 대조해 docs/기록/데이터가공/화자라벨_표본검사_20261001.csv에 적는다.
실행: python scripts/speaker_label_sample.py > 표본.txt   (API 호출 없음)
"""
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sillok_rag.corpus import load_chunks  # noqa: E402

PLAN = {"기타(확인필요)": 36, "문답": 15, "신하": 15, "임금": 10, "상소": 8, "서술": 8, "왕실": 4, "관청": 4}
SEED = 20261001


def sample(chunks):
    by = defaultdict(list)
    for c in chunks:
        by[c["speaker_kind"]].append(c)
    rnd = random.Random(SEED)
    out = []
    for kind, n in PLAN.items():
        out += sorted(rnd.sample(by[kind], min(n, len(by[kind]))), key=lambda c: c["chunk_id"])
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for i, c in enumerate(sample(load_chunks()), 1):
        print(f"### {i} {c['chunk_id']} [{c['speaker_kind']}] 초안={c['speaker_draft']} | 화자={c['speaker']} | 인용={c['quoted']}")
        print("원문:", c["original"])
        print("번역:", c["translation"])
        print()
