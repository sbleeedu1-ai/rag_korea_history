"""공공데이터 ZIP에서 골라 둔 실록 기사만 뽑아낸다.

사용법:
    python scripts/extract_articles.py /path/to/실록원문.zip

기사마다 XML 파일 하나를 data/raw_xml/ 에 저장하고, 요약본을
data/articles.jsonl (기사 id, 날짜, 제목, 출처 쪽수, 원문 텍스트)에 쓴다.
용량이 큰 ZIP 파일 자체는 저장소에 올리지 않는다.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTICLE_IDS = [
    "wda_12512030_002",
    "wda_12602016_001",
    "wda_12602020_001",
    "wda_12602021_001",
    "wda_12602028_001",
    "wda_12603002_001",
    "wda_12809029_004",
]


def volume_file(article_id: str) -> str:
    # wda_12602020_001 -> 2nd_wda_126.xml (세종 26년 권)
    return f"2nd_{article_id[:7]}.xml"


def element_text(el: ET.Element) -> str:
    """요소의 글자만 이어 붙인다. 원주(原註)도 본문 안에 그대로 남긴다."""
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def extract(zip_path: Path) -> list[dict]:
    out_dir = ROOT / "data" / "raw_xml"
    out_dir.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(zip_path)
    by_volume: dict[str, list[str]] = {}
    for aid in ARTICLE_IDS:
        by_volume.setdefault(volume_file(aid), []).append(aid)

    records = []
    for vol, ids in by_volume.items():
        raw = zf.read(vol).decode("utf-8")
        # DTD 파일이 함께 들어 있지 않으므로 DOCTYPE 줄을 지워야 ElementTree가 읽을 수 있다
        raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw)
        root = ET.fromstring(raw)
        for aid in ids:
            el = root.find(f".//level5[@id='{aid}']")
            if el is None:
                raise SystemExit(f"기사를 찾지 못함: {vol} 안에 {aid} 없음")
            (out_dir / f"{aid}.xml").write_text(
                ET.tostring(el, encoding="unicode"), encoding="utf-8"
            )
            bib = el.find("front/biblioData")
            date = bib.find("date/dateOccured").get("date")
            sources = [
                f"{s.find('mainTitle').get('type')} {s.find('mainTitle').text} {s.find('page').get('begin')}"
                for s in bib.findall("source")
            ]
            paragraphs = [element_text(p) for p in el.findall("text/content/paragraph")]
            records.append(
                {
                    "article_id": aid,
                    "date": date,
                    "title_ko": bib.find("title/mainTitle").text,
                    "sources": sources,
                    "subjects": [s.text for s in bib.findall("subjectClass")],
                    "paragraphs": paragraphs,
                }
            )
    records.sort(key=lambda r: ARTICLE_IDS.index(r["article_id"]))
    with open(ROOT / "data" / "articles.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return records


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    for r in extract(Path(sys.argv[1])):
        print(r["article_id"], r["date"], r["title_ko"], f'{sum(len(p) for p in r["paragraphs"])}자')
