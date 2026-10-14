"""로드맵 단계별 산출물 사본 모으기(작업기록 [218]).

원본은 제자리에 두고(코드가 읽거나 저장소 규칙상 자리가 정해진 파일이 많음), 제출·발표용으로 로드맵 단계별 폴더에
**사본**을 모은다. 원본이 바뀌면 사본이 낡으므로 제출 전에 다시 실행한다. 같은 내용이면 덮어써도 결과가 같다.
목록(README.md)에는 단계 · 로드맵 산출물 · 사본 · 원본 위치를 적고, 크거나 코드인 것(data/ 전체, 앱)은 위치만 적는다.

실행: python scripts/collect_deliverables.py
출력: docs/기록/제출/산출물/ (단계별 폴더 + README.md)
"""
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = ROOT / "docs" / "기록" / "제출" / "산출물"

# (단계 폴더, 로드맵 산출물, [(원본, 사본 이름 또는 None=원본 이름)], 사본 없이 위치만 적을 것)
STAGES = [
    ("1단계_주제확정", "제안서, 저장소 + README",
     [("docs/참고/역사인물인터뷰_한국사학습RAG_제안서.pdf", None), ("README.md", "README_저장소안내.md")],
     ["저장소: github.com/sbleeedu1-ai/rag_korea_history_test", "`.gitignore`에 `.env`·`chroma_db/`"]),
    ("2단계_데이터구축", "`data/` 폴더, 수집 가능한 코드, 데이터 표",
     [("docs/기록/데이터구축/데이터표.xlsx", None), ("scripts/extract_articles.py", None)],
     # 고른기사목록은 데이터표 '기사 목록' 시트에 모두 들어 있고, 고른 과정 설명은 데이터표의 한 줄 요약으로 갈음(사용자 2026-10-02)
     ["`data/` 전체(원문 XML 132건·코퍼스·평가셋, 약 63MB)는 저장소 그대로",
      "기사 고른 과정의 자세한 설명: `docs/기록/데이터구축/데이터구축.md`"]),
    # 로드맵 산출물 세 개로: CSV는 엑셀 시트로 묶고, 규칙서는 워드로(사용자 2026-10-02, 작업기록 [219])
    ("3단계_파싱정제청킹", "청크 통계표, 청크 수동 검사표, 정제 규칙서 (+ 청킹 전략 2개 이상 비교, 용어 풀이 검수표)",
     [(("xlsx", [("청크 통계(v2)", "docs/기록/데이터가공/청크통계_20260930_v2.csv",
                  "규칙서 v2로 자른 132건 803청크의 통계(원문 글자 수 기준). 원본: docs/기록/데이터가공/청크통계_20260930_v2.csv"),
                 ("전략별 길이 통계(9-29)", "archive/새코퍼스_1-4차_793청크/청크_v1b/청크비교_20260929_v1b_전략별통계.csv",
                  "청킹 전략 3가지로 같은 기사를 자른 통계(2026-09-29, 규칙서 v1.1 기준). 전략 B가 지금 방식"),
                 ("전략별 검색 비교(10-02)", "results/20261002_청킹전략검색/전략별요약.csv",
                  "번역된 지금 청크를 이어 붙인 세 전략의 검색 적중(질문 94개, 리랭커 없이). 같은 글자 양(3,500자)에서 지금 방식이 가장 좋음"),
                 ("정제 규칙 적용 횟수", "docs/기록/데이터가공/정제기록_20260930_v2.csv",
                  "기사마다 정제 규칙(교감·주석·사론 등)을 몇 번 적용했는지")]), "청크통계표.xlsx"),
      (("xlsx", [("수동 검사표(v2)", "docs/기록/데이터가공/수동검사표_20260930_v2.csv",
                  "803청크 중 무작위 25개를 정상/잘림/섞임/버림과 화자 맞음으로 판정(Claude 가판정 → 사람 확인)")]), "수동검사표.xlsx"),
      # 쉬운 말 풀이 검수표(사용자 2026-10-06, 작업기록 [285]): 사전 대조와 사람 검수 결과. 사전 문장은 없음
      (("xlsx", [("용어 풀이 검수표", "docs/기록/데이터가공/용어사전확인_20261006.csv",
                  "청크에 붙인 쉬운 말 풀이(gloss) 용어마다 처음 풀이·판정·고친 풀이·확인한 곳·메모. 표준국어대사전·한국민족문화대백과 대조와 사용자 검수(2026-10-06) 결과. 쓰는 기준은 규칙서 4-8")]), "용어풀이검수표.xlsx"),
      (("docx", "docs/기록/데이터가공/정제청킹_규칙서.md"), "정제청킹_규칙서.docx")],
     ["청킹 코드: `scripts/chunk_articles.py`, 전략 비교: `archive/scripts_20261008/chunk_strategy_retrieval.py`"]),
    # 로드맵 산출물 두 개(평가셋·채점표)를 엑셀로(사용자 2026-10-02, 작업기록 [220])
    ("4단계_평가셋", "평가셋, 채점표 (+ LLM 채점과 사람 채점 비교)",
     [(("xlsx-build", "deliverables_stage4:eval_sheets"), "평가셋.xlsx"), (("xlsx-build", "deliverables_stage4:grade_sheets"), "채점표.xlsx")],
     ["평가셋 원본: `data/eval/`, 설계: `docs/기록/평가셋/평가셋설계.md`",
      "채점 원본: `results/20261001_검색보강답변평가/`·`20261001_역할장면검색/`·`20261001_계유정난_새문항/`·`20261002_사람채점비교/`",
      "자동 실행·채점: `python -m sillok_rag.cli run-all`, `llm-grade`"]),
    # 로드맵 산출물 두 개: 실패 유형 집계표(엑셀), 그 표를 바탕으로 한 다음 테스트 계획(워드)(작업기록 [222])
    ("5단계_오답노트", "실패 유형 집계표, 이 표를 기반으로 한 다음 테스트 계획",
     [(("xlsx-build", "deliverables_stage5:failure_sheets"), "실패유형집계표.xlsx"),
      (("docx", "docs/기록/다음테스트계획_20261002.md"), "다음테스트계획.docx")],
     ["실험마다의 실패 분석: `docs/기록/오답노트.md`(파일럿 1-7차는 `archive/파일럿_1-7차/docs/오답노트.md`)"]),
    # 실험 로그를 엑셀 하나로(사용자 2026-10-02 "이거도 종합해서 하나로", 작업기록 [225]). 그래프는 나중에
    ("6단계_개선", "실험 로그(바꾸기 전 → 후, 채택/기각 이유), 그래프",
     [(("xlsx-build", "deliverables_stage6:log_sheets"), "실험로그.xlsx")],
     ["채택·기각 이유 전체: `docs/결정.md`, 시간순 기록: `docs/기록/작업기록.md`, 파일럿 표: `archive/README.md`",
      "개선 전후·ChatGPT 비교 PDF: `docs/기록/제출/개선전후_ChatGPT비교_20261001_이성빈.pdf`", "그래프: 아직 없음(나중에)"]),
    ("7단계_서비스화", "Streamlit 고도화",
     [("docs/참고/조선 기록실의 역사 취재록-2.png", "화면시안_1.png"), ("docs/참고/역사 취재록_ 언문 논쟁 인터뷰-1.png", "화면시안_2.png"),
      ("docs/기록/에피소드/튜토리얼_훈민정음_초안_20261001.md", None)],
     ["화면 코드: `app.py`(`streamlit run app.py`)"]),
    ("8단계_최종리포트", "최종 리포트", [], ["아직 없음"]),
]


def main():
    lines = [f"# 로드맵 단계별 산출물 (사본, {date.today():%Y-%m-%d} 기준)", "",
             "원본은 저장소 제자리에 있고, 이 폴더는 제출·발표용 **사본**입니다. 원본이 바뀌면 "
             "`python scripts/collect_deliverables.py`로 다시 모읍니다. 로드맵은 `docs/로드맵.md`.", "",
             "| 단계 | 로드맵 산출물 | 사본 (이 폴더) | 원본 위치 · 참고 |", "|---|---|---|---|"]
    # 원본이 모두 있는지 먼저 확인하고, 새 사본은 임시 폴더에 끝까지 모은 뒤 기존 폴더와 바꾼다.
    # 예전에는 기존 폴더부터 지워서 원본 하나가 없거나 변환이 실패하면 제출 사본이 사라졌다(전체검토 2-8 7번).
    missing = [src for _, _, files, _ in STAGES for src, _ in files
               if not isinstance(src, tuple) and not (ROOT / src).exists()]
    if missing:
        raise FileNotFoundError(f"원본이 없습니다(기존 사본은 그대로): {missing}")
    tmp, old = OUT.with_name(OUT.name + ".new"), OUT.with_name(OUT.name + ".old")
    if tmp.exists():   # 지난번 실패로 남은 임시 폴더
        shutil.rmtree(tmp)
    if old.exists():   # 지난번 교체가 중간에 멈춤: 사본 폴더가 없으면 옛 사본을 되살리고, 있으면 남은 옛 사본을 지운다
        if OUT.exists():
            shutil.rmtree(old)
        else:
            old.rename(OUT)
    n = 0
    for folder, roadmap, files, notes in STAGES:
        d = tmp / folder
        d.mkdir(parents=True, exist_ok=True)
        copied, sources = [], []
        for src, name in files:
            if isinstance(src, tuple):   # 사람이 보기 좋은 형식으로 바꿔 만든 사본(엑셀·워드)
                from office_export import csv_sheets_to_xlsx, md_to_docx
                kind, spec = src
                if kind == "xlsx-build":   # 단계별 모듈이 줄 목록을 만든다("모듈:함수")
                    import importlib
                    module, func = spec.split(":")
                    csv_sheets_to_xlsx(getattr(importlib.import_module(module), func)(), d / name)
                elif kind == "xlsx":
                    csv_sheets_to_xlsx([(sh, ROOT / p, note) for sh, p, note in spec], d / name)
                    sources += [f"`{p}`" for _, p, _ in spec]
                else:
                    md_to_docx(ROOT / spec, d / name, f"제출용 사본(원본: {spec}). 원본 문서 안의 링크는 글자만 남겼습니다.")
                    sources.append(f"`{spec}`")
            else:
                s = ROOT / src
                if not s.exists():
                    raise FileNotFoundError(src)
                shutil.copy2(s, d / (name or s.name))
                sources.append(f"`{src}`")
            copied.append(f"[{name or Path(src).name}]({folder}/{name or Path(src).name})")
            n += 1
        lines.append(f"| {folder.replace('_', ' ')} | {roadmap} | {'<br>'.join(copied) or '-'} | "
                     f"{'<br>'.join(sources + notes)} |")
    (tmp / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 이 폴더는 스크립트가 만드는 사본뿐이라, 목록에서 뺀 파일이 남지 않게 통째로 바꾼다.
    # 기존 폴더를 먼저 지우면 이름 바꾸기가 실패할 때 사본을 잃었다(코드정리검토 X2). 옆 이름으로 비켜 두고 바꾼 뒤에 지운다
    had_old = OUT.exists()
    if had_old:
        OUT.rename(old)
    try:
        tmp.rename(OUT)
    except Exception:
        if had_old:
            old.rename(OUT)
        raise
    if had_old:
        shutil.rmtree(old)
    print(f"사본 {n}개 → {OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
