"""문서 확장용 실록 기사를 ZIP에서 뽑아 데이터 표로 만든다 (2026-09-29).

사용법:
    python scripts/extract_expansion_articles.py /path/to/실록원문.zip

입력: data/expansion/후보기사목록_20260929.csv (주제묶음, 기사ID, 고른이유)
출력:
    data/raw_xml/{기사ID}.xml                기사 XML 원본 조각(파일럿과 같은 방식)
    data/expansion/articles_20260929.jsonl  기사 id, 날짜, 제목, 출처, 분류, 원문 문단
    data/expansion/데이터표_20260929.csv     주제·날짜·제목·원문 글자 수 한 줄 요약

파일럿(data/articles.jsonl, 세종 한글 창제 7건)은 건드리지 않는다.
기사 고른 근거는 docs/문서확장_한능검출제빈도_20260929.md 참고.
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
EXP = ROOT / "data" / "expansion"
RAW = ROOT / "data" / "raw_xml"
LIST_CSV = EXP / "후보기사목록_20260929.csv"

# XML 1.0에서 허용되지 않는 제어 문자 참조(&#1; 등). 일부 권에 들어 있어 그대로는 읽히지 않는다.
BAD_CHAR_REF = re.compile(r"&#(?:x0*(?:[0-8bcef]|1[0-9a-f])|0*(?:[0-8]|1[124-9]|2[0-9]|3[01]));", re.I)


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
    rows = list(csv.DictReader(open(LIST_CSV, encoding="utf-8")))
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

    with open(EXP / "articles_20260929.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(records[r["기사ID"]], ensure_ascii=False) + "\n")

    with open(EXP / "데이터표_20260929.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["순번", "주제묶음", "기사ID", "실록", "날짜", "제목", "원문글자수", "고른이유"])
        for i, r in enumerate(rows, 1):
            rec = records[r["기사ID"]]
            n_chars = len(re.sub(r"\s", "", "".join(rec["paragraphs"])))
            book = rec["sources"][0].split()[1] if rec["sources"] else ""
            w.writerow([i, r["주제묶음"], r["기사ID"], book, rec["date"][:10], rec["title_ko"], n_chars, r["고른이유"]])
    print(f"{len(rows)}건 추출 → {EXP.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
