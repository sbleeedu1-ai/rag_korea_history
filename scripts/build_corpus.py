"""챗봇이 읽는 코퍼스(기사 132건, 803청크)를 만든다 (규칙서 v2, 2026-09-30. 그전에는 v1.1로 793청크).

사용법:
    python scripts/build_corpus.py            # 코퍼스 만들기 + 진행 상황
    python scripts/build_corpus.py --dump 번호 [개수]
        # 번역할 기사 원문을 청크 단위로 보여 준다(번호는 data/articles.jsonl 순서, 0부터)

입력:
    data/청크초안_20260930_v2.jsonl                                규칙서로 자른 청크(원문)
    data/articles.jsonl                                           기사 132건(순서)
    data/번역/*.jsonl                                             청크별 번역(AI 초안, 규칙서 4-6). 001-012는 확장 125건,
                                                                  013은 훈민정음 창제 7건(파일럿 실험 때 기사를 규칙서 청크로 다시 번역한 것)
출력:
    data/corpus.jsonl                                             챗봇·실험·Chroma DB가 읽는 코퍼스

번역 파일 한 줄 = 청크 하나:
    chunk_id, speaker(한글(漢字)), quoted(목록), event_date, known_from, translation, note, gloss(쉬운 말 풀이 목록, 없으면 생략)
번역이 아직 없는 청크는 translation 빈칸, translation_status "untranslated"로 둔다.
머리말(header)은 규칙서 4-5 형식으로, 화자·인용을 한글 이름으로 바꿔 다시 만든다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sillok_rag.corpus import read_jsonl  # noqa: E402  (같은 내용의 함수가 여기에도 있던 것을 하나로, 코드정리검토 X27)

CHUNKS = ROOT / "data" / "청크초안_20260930_v2.jsonl"   # 규칙서 v2 (v1b는 2026-09-30까지)
ARTICLES = ROOT / "data" / "articles.jsonl"
TRANS_FILES = sorted((ROOT / "data" / "번역").glob("*.jsonl"))
OUT = ROOT / "data" / "corpus.jsonl"

TRANS_FIELDS = ("speaker", "quoted", "event_date", "known_from", "translation", "note", "gloss")


def all_chunks() -> list[dict]:
    order = {a["article_id"]: i for i, a in enumerate(read_jsonl(ARTICLES))}
    chunks = [c for c in read_jsonl(CHUNKS) if c["article_id"] in order]
    chunks.sort(key=lambda c: (order[c["article_id"]], c["chunk_id"]))
    return chunks


def load_translations() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in TRANS_FILES:
        for t in read_jsonl(path):
            if t["chunk_id"] in out:
                raise SystemExit(f"번역 중복: {t['chunk_id']} ({path.name})")
            out[t["chunk_id"]] = t
    return out


def date_label(date: str | None, reign: str, king: str, leap: bool) -> str:
    reign_label = reign if reign.startswith(king) else f"{king} {reign}"  # reign에 왕 이름이 이미 들어 있으면 겹치지 않게
    if not date:
        return reign_label
    y, m, d = date.split("-")
    return f"{int(y)}년 {'윤' if leap else ''}{int(m)}월 {int(d)}일 · {reign_label}"


def header(c: dict) -> str:
    parts = [date_label(c["record_date"], c["reign"], c["king"], c["leap_month"]), c["title_ko"], f"말한 사람: {c['speaker']}"]
    if c["quoted"]:
        parts.append("인용: " + "·".join(c["quoted"]))
    return "[" + " · ".join(parts) + "]"


def build() -> None:
    chunks = all_chunks()
    trans = load_translations()
    ids = {c["chunk_id"] for c in chunks}
    stray = sorted(set(trans) - ids)
    if stray:
        raise SystemExit(f"청크에 없는 번역 ID: {stray[:5]}")

    done = 0
    # 임시 파일에 끝까지 쓴 뒤 바꾼다. 중간에 오류가 나면 기존 corpus.jsonl이 그대로 남는다(전체검토 2-8 7번)
    part = OUT.with_name(OUT.name + ".part")
    with open(part, "w", encoding="utf-8") as f:
        for c in chunks:
            c = dict(c)
            c["speaker_draft"] = c["speaker"]  # 규칙서 자동 초안(한자)은 남겨 둔다
            t = trans.get(c["chunk_id"])
            if t:
                for k in TRANS_FIELDS:
                    if k in t or k in c:  # gloss는 풀이가 있는 청크에만 둔다
                        c[k] = t.get(k, c.get(k))
                c["translation_status"] = "ai_draft"
                done += 1
            else:
                c["translation"] = ""
                c["translation_status"] = "untranslated"
                c.setdefault("note", "")
            c["header"] = header(c)
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    part.replace(OUT)

    arts = {c["article_id"] for c in chunks}
    done_arts = {c["article_id"] for c in chunks if c["chunk_id"] in trans}
    full = {a for a in done_arts if all(x["chunk_id"] in trans for x in chunks if x["article_id"] == a)}
    print(f"{OUT.relative_to(ROOT)}: 청크 {len(chunks)}개 중 번역 {done}개, 기사 {len(arts)}건 중 번역 끝 {len(full)}건")


def dump(start: int, count: int) -> None:
    arts = read_jsonl(ARTICLES)[start:start + count]
    chunks = all_chunks()
    for i, a in enumerate(arts, start):
        print(f"### [{i}] {a['article_id']} {a['date']} {a['title_ko']}")
        for c in chunks:
            if c["article_id"] != a["article_id"]:
                continue
            q = f" 인용:{c['quoted']}" if c["quoted"] else ""
            tw = f" 시점:{c['time_words']}" if c["time_words"] else ""
            print(f"- {c['chunk_id']} | {c['speaker_kind']}:{c['speaker']}{q}{tw}\n  {c['original']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--dump":
        dump(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    else:
        build()
