"""기사 목록에 있는 실록 기사를 원문 ZIP에서 뽑아 기사 파일과 데이터 표를 만든다.

사용법:
    python scripts/extract_articles.py /path/to/실록원문.zip

원문 ZIP(공공데이터포털 조선왕조실록 원문, 137MB)은 저장소에 없고 사용자 컴퓨터에 있다.
기사를 늘리거나 바꿀 때는 docs/기록/데이터구축/고른기사목록.csv 끝에 줄을 더하고 이 스크립트를 다시 실행한다.
원문 ZIP에서 기사를 뽑을 때 한 번만 쓰는 목록이라 사람용 기록 폴더에 둔다(2026-10-01, 작업기록 [140]).
다음 단계(청킹·코퍼스)는 이 목록이 아니라 여기서 만든 data/articles.jsonl을 읽는다.

입력: docs/기록/데이터구축/고른기사목록.csv (주제묶음, 기사ID, 고른이유) — 132건. 파일럿/확장 구분은 2026-10-01에 없앰(작업기록 [139])
출력 (실행할 때마다 새로 씀):
    data/raw_xml/{기사ID}.xml   기사 XML 원본 조각
    data/articles.jsonl         기사 id, 주제, 날짜, 제목, 출처, 분류, 원문 문단
데이터 표(docs/기록/데이터구축/데이터표.csv)는 청크 수·번역 글자 수가 필요해서 청킹 뒤에 scripts/data_table.py가 만든다([215]).

기사 고른 근거는 docs/데이터.md 참고.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw_xml"
LIST_CSV = ROOT / "docs" / "기록" / "데이터구축" / "고른기사목록.csv"

# XML 1.0에서 허용되지 않는 제어 문자 참조(&#1; 등). 일부 권에 들어 있어 그대로는 읽히지 않는다.
BAD_CHAR_REF = re.compile(r"&#(?:x0*(?:[0-8bcef]|1[0-9a-f])|0*(?:[0-8]|1[124-9]|2[0-9]|3[01]));", re.I)


def read_list(path: Path = LIST_CSV) -> list[dict]:
    """기사 목록을 읽는다. 순서가 곧 articles.jsonl과 청크 파일의 순서다."""
    return list(csv.DictReader(open(path, encoding="utf-8")))


def volume_file(article_id: str) -> str:
    # wda_12602020_001 -> 2nd_wda_126.xml, 총서 waa_000084 -> 2nd_waa_000.xml
    return f"2nd_{article_id[:7]}.xml"


def element_text(el: ET.Element) -> str:
    """요소의 글자만 이어 붙인다. 원주(原註)도 본문 안에 그대로 남긴다."""
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def load_volume(zf: zipfile.ZipFile, name: str) -> ET.Element:
    raw = zf.read(name).decode("utf-8", "replace")
    raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw)  # DTD 파일이 ZIP에 없어서 지워야 읽힌다
    return ET.fromstring(BAD_CHAR_REF.sub("", raw))


def main(zip_path: Path) -> None:
    rows = read_list()
    zf = zipfile.ZipFile(zip_path)
    RAW.mkdir(parents=True, exist_ok=True)
    by_volume: dict[str, list[dict]] = {}
    for r in rows:
        by_volume.setdefault(volume_file(r["기사ID"]), []).append(r)

    records = {}
    for vol, items in by_volume.items():
        root = load_volume(zf, vol)
        for r in items:
            aid = r["기사ID"]
            # 보통 기사는 level5, 태조실록 총서(_000)는 level3이 기사 단위다
            el = root.find(f".//*[@id='{aid}']")
            if el is None:
                raise SystemExit(f"기사를 찾지 못함: {vol} 안에 {aid} 없음")
            (RAW / f"{aid}.xml").write_text(ET.tostring(el, encoding="unicode"), encoding="utf-8")
            bib = el.find("front/biblioData")
            d = bib.find("date/dateOccured")
            sources = [
                f"{s.find('mainTitle').get('type')} {s.find('mainTitle').text} {s.find('page').get('begin')}"
                for s in bib.findall("source")
            ]
            paragraphs = [element_text(p) for p in el.findall("text/content/paragraph")]
            records[aid] = {
                "article_id": aid,
                "topic": r["주제묶음"],
                "date": d.get("date") if d is not None else "총서",
                "title_ko": (bib.find("title/mainTitle").text or "").strip(),
                "sources": sources,
                "subjects": [s.text for s in bib.findall("subjectClass")],
                "paragraphs": paragraphs,
            }

    with open(DATA / "articles.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(records[r["기사ID"]], ensure_ascii=False) + "\n")

    print(f"{len(rows)}건 추출 → data/articles.jsonl, data/raw_xml/ (데이터 표는 청킹 뒤 scripts/data_table.py)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
