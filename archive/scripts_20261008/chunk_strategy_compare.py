"""청킹 전략 비교 (로드맵 3단계 '청킹 2개 이상'): 같은 기사를 세 방식으로 잘라 통계를 나란히 낸다 (2026-09-29).

사용법:
    python scripts/chunk_strategy_compare.py --tag <새 이름>

입력은 chunk_articles.py와 같이 data/raw_xml/ 이다(2026-09-30부터 원문 ZIP 필요 없음, 작업기록 [136]).

기사는 data/articles.jsonl(132건)의 순서를 쓴다. 지금 쓰는 결과는 --tag 20260929_v1b 로 낸 것이다.

전략
    참고: 길이만   — 화자와 상관없이 기사 원문을 400자 안팎으로 문장 끝에서 자름 (가장 단순한 기준선)
    A: 문단·화자   — 파일럿 23청크 코퍼스의 기준을 자동화 (기사→문단→말머리·翌日→상소 조목→길이)
    B: A + 인용 단위 + 머리말 — 규칙서 v1 (docs/기록/데이터가공/정제청킹_규칙서.md)

검색 성능 비교는 여기서 하지 않는다(나중에 실험에서 같은 평가셋으로).
출력 (덮어쓰지 않음. 비교용이라 코드가 읽지 않으므로 모두 docs/기록/데이터가공/):
    청크초안_20260929_v1b_전략A_문단화자.jsonl
    청크초안_20260929_v1b_참고_길이만.jsonl
    청크비교_20260929_v1b_전략별통계.csv
전략 B의 청크는 chunk_articles.py 결과(청크초안_20260929_v1b.jsonl)와 같다.
위 파일들은 v1.1 규칙 기준이라 2026-09-30에 archive/새코퍼스_1-4차_793청크/청크_v1b/ 로 옮겼다.
전략 비교 코드는 규칙서 v2의 새 규칙(날짜로 끊기, 사람 경계 등)을 아직 따르지 않는다. 검색 비교 때 맞춘다.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chunk_articles as t  # noqa: E402

OUT = t.REC


def length_only(aid: str, el) -> list[dict]:
    """화자를 보지 않고 기사 원문을 문장 끝에서 400자 안팎으로 자른다."""
    fl = t.Flattener()
    cnt: Counter = Counter()
    paras = [t.clean(fl.text(p), cnt) for p in el.findall("text/content/paragraph")]
    paras = [p for p in paras if p and not t.VOLUME_END.search(p)] + [t.clean(x, cnt) for x in fl.sanlon]
    text = " ".join(paras).lstrip("○◎ ")
    text = t.DAY_GANJI.sub("", text)
    meta = t.article_meta(aid, el)
    return [{"chunk_id": f"{aid}-{k:02d}", "article_id": aid, "title_ko": meta["title_ko"],
             "original": part, "n_chars": t.nlen(part)}
            for k, part in enumerate(t.split_long(text), 1)]


def row(name: str, chunks: list[dict], n_articles: int) -> list:
    ls = [c["n_chars"] for c in chunks]
    return [name, len(ls), round(len(ls) / n_articles, 1), round(statistics.mean(ls), 1), int(statistics.median(ls)),
            min(ls), max(ls), sum(n < t.MIN_LEN for n in ls), sum(n > t.MAX_LEN for n in ls),
            sum(1 for c in chunks if c.get("speaker_kind") in ("문답",) or c.get("mixed"))]


def main() -> None:
    ids = t.article_ids()
    base = t.TAG
    files = {"A": OUT / f"청크초안_{base}_전략A_문단화자.jsonl",
             "L": OUT / f"청크초안_{base}_참고_길이만.jsonl",
             "stats": OUT / f"청크비교_{base}_전략별통계.csv"}
    for f in files.values():
        if f.exists():
            raise SystemExit(f"이미 있음(덮어쓰지 않음): {f.relative_to(t.ROOT)}")

    res: dict[str, dict[str, list]] = {"L": {}, "A": {}, "B": {}}
    for aid in ids:
        el = t.load_article(aid)
        res["L"][aid] = length_only(aid, el)
        res["A"][aid] = t.process_article(aid, el, quote_split=False)[0]
        res["B"][aid] = t.process_article(aid, el, quote_split=True)[0]

    for key in ("A", "L"):
        with open(files[key], "w", encoding="utf-8") as f:
            for aid in ids:
                for c in res[key][aid]:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")

    names = {"L": "참고: 길이만", "A": "전략 A: 문단·화자(기존 기준)", "B": "전략 B: A + 인용 단위 + 머리말"}
    header = ["전략", "청크수", "기사당청크", "평균글자", "중앙값", "최단", "최장",
              f"{t.MIN_LEN}자미만", f"{t.MAX_LEN}자초과", "문답청크"]
    rows = [header]
    for key in ("L", "A", "B"):
        chunks = [c for a in ids for c in res[key][a]]
        rows.append([f"전체 {len(ids)}건 · {names[key]}", *row("", chunks, len(ids))[1:]])
    with open(files["stats"], "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    if t.take_tag(sys.argv[1:]):
        raise SystemExit(__doc__)
    main()
