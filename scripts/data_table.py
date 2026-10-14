"""데이터 표 만들기: 로드맵 2단계 산출물(작업기록 [215]).

로드맵: "데이터 표(출처, 수집일, 문서 수, 총 글자 수, 실제 사용 문서, 제외한 문서 등을 엑셀 같은 표에 정리)".
엑셀 파일 하나에 한눈에 보는 '데이터 현황' 시트와 근거 시트 둘(기사 목록·제외 목록)을 둔다. 현황의 합계는
근거 시트를 가리키는 수식이라 근거가 바뀌면 함께 바뀐다(엑셀이 열 때 계산).
실록 원문은 다시 받을 일이 없어 수집일은 적지 않는다(사용자 2026-10-02). 원문 ZIP 기준일만 출처 판을 가리키려고 남긴다.

원문 ZIP 없이 저장소 파일만 읽는다(비용 없음). 청크 수·번역 글자 수가 필요해서 원문 추출(extract_articles.py)이
아니라 청킹·코퍼스를 만든 뒤에 돌린다.

입력: docs/기록/데이터구축/고른기사목록.csv, data/articles.jsonl, data/corpus.jsonl,
      docs/기록/데이터구축/한능검_정답의_실록수록_확인_20260929.csv
출력: docs/기록/데이터구축/데이터표.xlsx (사람이 보는 표, 코드는 안 읽음)

실행: python scripts/data_table.py
"""
import collections
import csv
import json
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "기록" / "데이터구축"
LIST_CSV = OUT / "고른기사목록.csv"
CHECK_CSV = OUT / "한능검_정답의_실록수록_확인_20260929.csv"
FREQ_CSV = OUT / "한능검_출제빈도_문항별_20260929.csv"

ZIP_NAME = "교육부 국사편찬위원회_조선왕조실록 정보_실록원문"
ZIP_DATE = "2026-08-21"        # 원문 ZIP 기준일(파일 이름)
ZIP_ARTICLES = 381_144         # ZIP 전체 기사 수(데이터구축.md 5절, 제목·날짜 색인)

FONT = "Arial"
HEAD = PatternFill("solid", start_color="E8ECEF")
THIN = Side(style="thin", color="B7BDC4")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def nchars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def style_table(ws, first_row, last_row, ncols):
    for r in ws.iter_rows(min_row=first_row, max_row=last_row, max_col=ncols):
        for c in r:
            c.font = Font(name=FONT, bold=c.row == first_row, size=10)
            c.border = BOX
            c.alignment = Alignment(vertical="top", wrap_text=True)
            if c.row == first_row:
                c.fill = HEAD
    # 글자 길이에 맞춘다(수식은 결과만 보이므로 짧게, 한글은 2칸. 고정 폭 목록은 2026-10-02부터 안 씀)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from office_export import display_width
    for i in range(1, ncols + 1):
        w = max((display_width(ws.cell(row=r, column=i).value) for r in range(first_row, last_row + 1)
                 if ws.cell(row=r, column=i).value is not None), default=6)
        ws.column_dimensions[chr(64 + i)].width = min(max(w + 2, 6), 50)
    ws.freeze_panes = ws.cell(row=first_row + 1, column=1)


def main():
    picks = list(csv.DictReader(open(LIST_CSV, encoding="utf-8")))
    arts = {a["article_id"]: a for a in map(json.loads, open(ROOT / "data" / "articles.jsonl", encoding="utf-8"))}
    chunks = collections.defaultdict(list)
    for c in map(json.loads, open(ROOT / "data" / "corpus.jsonl", encoding="utf-8")):
        chunks[c["article_id"]].append(c)
    check = list(csv.DictReader(open(CHECK_CSV, encoding="utf-8-sig")))
    n_questions = sum(1 for _ in csv.DictReader(open(FREQ_CSV, encoding="utf-8-sig")))
    excluded = [r for r in check if r["판정"] == "없음"]

    wb = Workbook()
    # ── 근거 시트 1: 기사 목록 ──
    ws_a = wb.active
    ws_a.title = "기사 목록"
    head = ["순번", "주제묶음", "기사ID", "실록", "날짜", "제목", "원문 글자 수", "번역 글자 수", "청크 수", "고른 이유"]
    ws_a.append(head)
    for i, p in enumerate(picks, 1):
        a, cs = arts[p["기사ID"]], chunks[p["기사ID"]]
        book = a["sources"][0].split()[1] if a["sources"] else ""
        ws_a.append([i, p["주제묶음"], p["기사ID"], book, a["date"][:10], a["title_ko"],
                     nchars("".join(a["paragraphs"])), sum(nchars(c["translation"]) for c in cs), len(cs), p["고른이유"]])
    last = ws_a.max_row
    ws_a.append(["합계", "", f"=COUNTA(C2:C{last})", "", "", "", f"=SUM(G2:G{last})", f"=SUM(H2:H{last})",
                 f"=SUM(I2:I{last})", "글자 수는 공백을 뺀 수"])
    style_table(ws_a, 1, ws_a.max_row, len(head))
    for c in ws_a[ws_a.max_row]:
        c.font = Font(name=FONT, bold=True, size=10)
    for row in ws_a.iter_rows(min_row=2, min_col=7, max_col=9):
        for c in row:
            c.number_format = "#,##0"
    total = ws_a.max_row      # 합계 행

    # ── 근거 시트 2: 제외 목록 ──
    ws_x = wb.create_sheet("제외 목록")
    ws_x.append(["회차", "문항", "정답 내용(우리말 요약)", "제외 이유"])
    for r in excluded:
        ws_x.append([int(r["회차"]), int(r["문항"]), r["정답 내용(우리말 요약)"],
                     "실록 원문에서 정답 근거를 찾지 못해 기사를 넣지 않음. " + r["근거(기사ID·메모)"]])
    xlast = ws_x.max_row
    style_table(ws_x, 1, xlast, 4)

    # ── 한눈에 보는 시트: 데이터 현황 ──
    ws = wb.create_sheet("데이터 현황", 0)
    ws["A1"] = "데이터 현황 (로드맵 2단계 데이터 표)"
    ws["A1"].font = Font(name=FONT, bold=True, size=13)
    cols = ["자료", "출처", "이용 조건", "기준일", "전체 문서 수", "실제 사용 문서 수", "총 글자 수", "제외한 문서 수", "제외·비고"]
    ws.append([])
    ws.append(cols)                                   # 3행
    ws.append(["조선왕조실록 원문(한문 XML)", f"국사편찬위원회, 공공데이터포털 '{ZIP_NAME}'", "공공누리 제1유형 + AI 활용 허용",
               ZIP_DATE, ZIP_ARTICLES, f"='기사 목록'!C{total}", f"='기사 목록'!G{total}", "=E4-F4",
               "한능검 조선 문항의 주제·정답 근거에 해당하는 기사만 골라 씀(나머지는 고르지 않음). 태조-철종. "
               "XML 제어 문자(깨진 글자)는 추출 때 지움, 스캔본 없음. 글자 수는 고른 기사의 원문"])
    ws.append(["한능검 심화 65-79회 기출(기사 고르는 기준)", "국사편찬위원회 한국사능력검정시험 자료실", "공공누리 제4유형(문항 원문은 저장소에 넣지 않음)",
               "-", n_questions, "=E5-H5", "-", f"=COUNTA('제외 목록'!A2:A{xlast})",
               "조선(태조-철종) 문항만 셈. 제외: 실록에서 정답 근거를 찾지 못한 문항(제외 목록 시트). 고종 이후·고려 문항은 처음부터 셈에서 뺌"])
    ws.append(["우리 번역·청크(가공 결과)", "직접 번역: 한문 원문만 보고 AI 초안 + 사람 검수 242곳", "프로젝트 산출물(국역·신역은 넣지 않음)",
               "-", f"='기사 목록'!C{total}", f"='기사 목록'!C{total}", f"='기사 목록'!H{total}", 0,
               f"=\"청크 \"&TEXT('기사 목록'!I{total},\"#,##0\")&\"개(정제·청킹 규칙서 v2)\""])
    style_table(ws, 3, 6, len(cols))
    for row in ws.iter_rows(min_row=4, max_row=6, min_col=5, max_col=8):
        for c in row:
            c.number_format = "#,##0"
            c.alignment = Alignment(horizontal="right", vertical="top")
    ws["E4"].comment = Comment("실록 원문 ZIP 전체 기사 수. 출처: 데이터구축.md 5절(제목·날짜 색인을 만들 때 셈)", "Claude")
    ws["E5"].comment = Comment("한능검 심화 65-79회 중 조선(태조-철종) 문항 수. 출처: 한능검_출제빈도_문항별_20260929.csv", "Claude")
    ws["A8"] = "수집일은 적지 않음: 실록 원문은 다시 받을 일이 없음(원문 ZIP 기준일로 판을 구분). 근거는 '기사 목록'·'제외 목록' 시트, 합계는 그 시트를 가리키는 수식."
    ws["A8"].font = Font(name=FONT, size=9, italic=True)
    ws.freeze_panes = None
    # 근거 시트로 바로 가는 링크(시트 탭을 못 찾을 때, 사용자 2026-10-02)
    link = Font(name=FONT, size=10, color="0563C1", underline="single")
    def go(cell, sheet):  # 같은 파일 안 시트로 가는 링크(location 방식이라 엑셀에서 바로 이동)
        # display를 함께 줘야 구글 시트가 칸 글자 대신 '#gid=…'를 보여 주지 않는다(사용자 2026-10-02 확인)
        cell.hyperlink = Hyperlink(ref=cell.coordinate, location=f"'{sheet}'!A1", display=str(cell.value))

    for cell, sheet, text in (("A10", "기사 목록", "→ 기사 목록 시트 보기(기사 132건)"),
                              ("A11", "제외 목록", "→ 제외 목록 시트 보기(제외한 한능검 문항 17개)")):
        ws[cell] = text
        go(ws[cell], sheet)
        ws[cell].font = link
    for sheet in (ws_a, ws_x):  # 근거 시트에서 돌아가는 링크(표 오른쪽 위)
        c = sheet.cell(row=1, column=sheet.max_column + 2, value="← 데이터 현황으로")
        go(c, "데이터 현황")
        c.font = link

    path = OUT / "데이터표.xlsx"
    wb.save(path)
    # 엑셀이 계산할 값을 여기서도 셈해 보여 준다(수식 확인용)
    n_art = len(picks)
    print(f"저장: {path}")
    print(f"실록: 전체 {ZIP_ARTICLES:,} / 사용 {n_art} / 제외 {ZIP_ARTICLES - n_art:,} / 원문 {sum(nchars(''.join(arts[p['기사ID']]['paragraphs'])) for p in picks):,}자")
    print(f"한능검: 문항 {n_questions} / 제외 {len(excluded)} / 사용 {n_questions - len(excluded)}")
    print(f"번역: 기사 {n_art} / {sum(nchars(c['translation']) for cs in chunks.values() for c in cs):,}자 / 청크 {sum(len(cs) for cs in chunks.values())}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
