"""번역 청크(data/corpus.jsonl, 기사 132건·803청크, 규칙서 v2)와 기사 메타데이터를 읽는다."""
import json
import re
from pathlib import Path

from . import config


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_chunks(path: Path = config.CORPUS_PATH) -> list[dict]:
    chunks = read_jsonl(path)
    for c in chunks:
        c["known_key"] = known_key(c.get("known_from"))
    return chunks


_DATE = re.compile(r"(\d{4})(?:-(윤)?(\d{1,2}))?(?:-(\d{1,2}))?")


def known_key(when: str | None) -> float | None:
    """'인물이 알게 된 때'(known_from)나 장면 시점을 크기를 비교할 수 있는 숫자로 바꾼다. 시점 필터(D1·D2)에 쓴다.

    예) "1444-02-20" → 14440220.1, "1444-02-20 이전" → 14440220.0, "1444-02-20 오후" → 14440220.2,
        "1443-12" → 14431200.1(월만 알면 그 달 맨 앞, 是月 기사에만 씀),
        "1392~1398" → 13981231.1, "1592-05-06~05-29" → 15920529.1(범위는 **끝**으로 연다, 규칙서 v2 ㉔),
        "1795-윤02-12" → 17950262.1(윤달은 같은 달 뒤로), "후일 기록(사론)" → None(역할 대화에서는 늘 뺀다).
    같은 날 안에서 순서를 나눠야 할 때만 '오후'를 쓴다(예: 상소를 올린 뒤 같은 날 논박·하옥).
    '후일 기록'은 장면보다 뒤에 쓴 글(사론·졸기·총평·원주의 뒷날 평가·편찬 때 덧붙임)이라 당시 인물은 모른다.
    2026-09-30까지 이름은 '인물 모름'이었다(옛 결과 파일을 읽을 수 있게 둘 다 받는다).
    """
    if not when or "후일 기록" in when or "인물 모름" in when:
        return None
    if "~" in when:  # 범위: 끝 날짜로. 여러 해·여러 날에 걸친 청크가 시작 날짜부터 보이면 미래 정보가 샌다
        start, end = when.split("~", 1)
        end = re.match(r"[\d윤-]+", end.strip())
        sm = _DATE.search(start)
        if end and sm:
            parts = end.group().strip("-").split("-")
            y, leap, mo, d = sm.groups()
            leap = bool(leap)
            if len(parts[0]) == 4:                          # 끝에 연도가 있음: 1476~1504, 1592-05~1592-07-06
                y, mo, d = parts[0], (parts[1] if len(parts) > 1 else "12"), (parts[2] if len(parts) > 2 else "31")
                leap = "윤" in mo
            elif len(parts) >= 2:                           # 05-29: 연도는 시작에서
                mo, d, leap = parts[0], parts[1], "윤" in parts[0]
            else:                                           # 29: 연도·달은 시작에서
                d = parts[0]
            return int(y) * 10000 + int(mo.replace("윤", "")) * 100 + (50 if leap else 0) + int(d) + 0.1
    m = _DATE.search(when)
    if not m:
        return None
    year, leap, month, day = m.groups()
    key = int(year) * 10000 + int(month or 0) * 100 + (50 if leap else 0) + int(day or 0)
    rest = when[m.end():]
    if "이전" in rest:
        return key + 0.0
    if "오후" in rest:
        return key + 0.2
    if "이후" in rest:
        return key + 0.3
    return key + 0.1


def load_articles(path: Path = config.ARTICLES_PATH) -> list[dict]:
    return read_jsonl(path)


def cite(chunk: dict) -> str:
    """사람이 읽는 출처 표기. 예: wda_12602020_001 9문단 (청크의 paragraphs는 0부터 세므로 1을 더해 보여 준다)"""
    paras = "·".join(str(p + 1) for p in chunk["paragraphs"])
    return f"{chunk['article_id']} {paras}문단"


_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0002ffff]")


def han_only(text: str) -> str:
    """한자만 남긴다. 인용 대조에 쓴다."""
    return "".join(_CJK.findall(text))


def search_text(chunk: dict) -> str:
    """검색에 쓰는 텍스트: 제목 + 화자 + 번역문."""
    return f"{chunk['title_ko']} / {chunk['speaker']}\n{chunk['translation']}"


def corpus_fingerprint(chunks: list[dict]) -> str:
    """검색에 영향을 주는 값(청크 ID·검색 텍스트·시점 키)으로 만든 짧은 지문.

    Chroma DB를 만들 때 함께 저장해 두고, 실행 전에 지금 코퍼스와 같은지 비교한다.
    청크를 다시 나누거나 번역·시점을 고친 뒤 DB를 다시 만들지 않으면 옛 본문으로 검색·시점 필터를 하게 된다
    (2026-09-30 일일 검토: 793청크 DB와 803청크 코퍼스가 섞여 있었음). 실행 결과에도 적어 어느 코퍼스로 돌렸는지 남긴다.
    """
    import hashlib

    h = hashlib.sha256()
    for c in sorted(chunks, key=lambda c: c["chunk_id"]):
        h.update(f"{c['chunk_id']}\t{search_text(c)}\t{c.get('known_key')}\n".encode("utf-8"))
    return h.hexdigest()[:12]


def sillok_url(article_id: str) -> str:
    """데이터의 wda_ ID를 실록 사이트 주소(kda_)로 바꾼다. 링크만 달고 국역 본문은 가져오지 않는다."""
    return "https://sillok.history.go.kr/id/k" + article_id[1:]
