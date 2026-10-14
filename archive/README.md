# 아카이브 (지난 작업 보관)

지금 작업에는 쓰지 않지만 기록으로 남겨 두는 파일입니다. 2026-09-29에 새 코퍼스(기사 132건)와 평가셋 v3로 넘어가면서, 2026-09-30에 규칙서 v2(803청크)로 넘어가면서 옮겼습니다.
무엇을 왜 바꿨는지의 흐름은 [작업기록](../docs/기록/작업기록.md)에 있고, 여기에는 그 근거가 된 문서·채점표·원자료가 있습니다. **지우지 않고 옮기기만 했습니다.**

| 폴더 | 내용 |
|---|---|
| `파일럿_1-7차/` | 파일럿(기사 7건, 23청크)으로 한 개선 실험 1-7차의 결과 문서, 오답노트, 채점표, 원자료, 채점 스크립트 |
| `지난정리문서/` | 역할이 끝난 정리 문서와 옛 사본, 한 번 쓰고 결정이 끝난 비교 문서 |
| `기사목록_합치기전/` | 파일럿 7건·확장 125건을 따로 뽑던 때의 추출 스크립트 2개와 확장분 목록·기사 파일·데이터 표. 지금은 `docs/기록/데이터구축/고른기사목록.csv` 하나와 `scripts/extract_articles.py` 하나로 합침(내용은 같음) |
| `청크시험_v1_121건/` | 규칙서 첫 시험(121건) 결과. 132건으로 다시 낸 v1b가 대신하고, 겹치는 121건의 청크는 한 글자도 같음. 수동 검사표는 처음엔 `data/chunk_trial/`에 남겼다가 지금은 `새코퍼스_1-4차_793청크/청크_v1b/`에 있음 |
| `평가셋_만든과정/` | 평가셋 v3의 재료: 초안 49문항, v2 41문항, 만든 스크립트 3개, 옛 설계 문서 2개. 스크립트는 기록용이라 이 자리에서는 돌아가지 않음(경로가 옛 위치 기준) |
| `새코퍼스_1-4차_793청크/` | 규칙서 v1.1(793청크) 시절 자료: 새 코퍼스 1-4차 실행·채점 결과 84개(`results/`), v1b 청크·통계·정제기록·수동 검사표 v1(사람확인 포함)·청킹 전략 비교(`청크_v1b/`), v1b → v2로 번역과 정답 청크를 옮긴 도구 2개(`scripts/`, 한 번만 쓴 것이라 이 자리에서는 돌아가지 않음), 규칙서 v1.1 원문과 v2 변경 기록. 결과 파일은 예전 청크 ID를 쓰며, 새 ID는 `archive/새코퍼스_1-4차_793청크/청크_v1b/청크대응_20260930_v2.csv`로 찾음. 2026-09-30 옮김(작업기록 [123]) |

## 파일럿 1-7차 한눈에 보기

기사 7건(23청크), 평가 단발 25문항 + 다회차 시나리오 A·B·C(30턴), `gpt-4o-mini-2024-07-18`, temperature 0, 한 번씩 실행.
맞음 = 정답 + 적절한 보류. 숫자는 조건 C / D1 / D2 순서입니다(조건 설명은 `파일럿_1-7차/docs/EXPERIMENT.md`).

| 차수 | 날짜 | 바꾼 것 | 단발 맞음 /25 | 역할 맞음 /30 | 채택 | 결과 문서 | 작업기록 |
|---|---|---|---|---|---|---|---|
| 1차 | 09-28 | 파일럿 첫 실행(조건 A-D2) | 13 / 12 / 13 | 21 / 23 / 22 | 기준 | `docs/PILOT_RESULT_20260928.md` | [13] |
| 2차 | 09-29 | 역할 프롬프트 v2 + 아는 사실 카드 | 14 / 13 / 13 | 22 / 24 / 23 | 카드는 채택, 말버릇 부작용 | `docs/실험결과_20260929_v2_…md`, `docs/실패사례_20260929_v2_…md` | [23], [25] |
| 3차 | 09-29 | 말투 수정(프롬프트 v3) + top_k 4 vs 8 | 14 / 14 / 13 (k8: 14 / 15 / 14) | 21 / 24 / 23 (k8: 19 / 23 / 22) | 말투 수정 채택, top_k 4 유지 | `docs/실험결과_20260929_v3_…md` | [32] |
| 4차 | 09-29 | 하이브리드 검색(임베딩 + BM25) | 15 / 16 / 15 | 22 / 23 / 22 | **채택** (검색 적중 16 → 19 /21) | `docs/실험결과_20260929_v4_…md` | [37] |
| 5차 | 09-29 | 사실 질문 규칙 v4(과잉 보류 줄이기) | **19 / 19 / 18** | 23 / 26 / 23 | **채택** | `docs/실험결과_20260929_v5_…md` | [43] |
| 6차 | 09-29 | 아는 사실 카드를 대화 첫 턴에(프롬프트 v5) | 5차와 같음(다시 안 돌림) | 22 / 24 / 21 | 채택 안 함 | `docs/실험결과_20260929_v6_…md` | [47] |
| 7차 | 09-29 | 먼저 전제 판정 + 중립 검색어(`--precheck`) | 5차와 같음(다시 안 돌림) | 21 / 24 / 25 | 기본값으로 안 켬 | `docs/실험결과_20260929_v7_…md` | [61] |

- 판정은 모두 Claude 가채점입니다. 사람이 확인한 건 1차의 핵심 10문항(50행)뿐입니다.
- 한 번씩만 돌려서 1-2문항 차이는 흔들림일 수 있습니다.
- 실험 차수와 프롬프트 버전은 번호가 다릅니다. 5차 = 프롬프트 v4, 6차 = 프롬프트 v5입니다. 결과 파일의 `prompt_version`은 프롬프트 버전입니다.

### 지금 코드에 남은 것 (파일럿에서 정한 기본값)

- 검색: 하이브리드, top_k 4 (4차)
- 사실 질문 규칙 v4, 역할 규칙 v3, 아는 사실 카드는 시스템 프롬프트에 (`PROMPT_VERSION = "v4"`, `FACTS_IN = "system"`)
- 시점 필터(D1·D2): 미래 누설 0건이 1-7차 내내 유지됨
- 조건 A(원문만)는 개선 실험에서 제외, 비교 기준으로만 둠
- 선택지로 남겼다가 2026-09-29 정리 때 지운 것: 카드 첫 턴(`FACTS_IN = "turn"`, 6차), 사전 판정(`--precheck`, 7차), 조건 A·B. 코드는 커밋 `c39ee69`에 있음(작업기록 [105])

### 새 코퍼스에서 다시 확인할 것

- 틀린 전제 받아들이기(전제 교정 6문항)는 1-7차 내내 풀리지 않았습니다. 생략된 주어 보충(규칙서 T 규칙)과 청크 품질로 나아지는지 봅니다.
- 시점 필터를 `event_order` 대신 `known_from`으로 거르기(`docs/정제청킹_규칙서.md`, 오답노트 ⑥·⑦)
- 뒤로 미룬 것: 임베딩 large, 같은 조건 반복 실행, 하이브리드 가중치

## 파일럿 폴더 안내

폴더 안의 문서에 적힌 경로(`docs/…`, `results/…`, `scripts/…`)는 **`파일럿_1-7차/` 폴더 기준**으로 읽으면 맞습니다. 폴더 구조를 그대로 옮겨 왔기 때문입니다.

| 경로 | 내용 |
|---|---|
| `docs/EXPERIMENT.md` | 파일럿 실험 설계(조건 A-D2, 판정 규칙, 사건 시점 번호) |
| `docs/PILOT_RESULT_20260928.md`, `docs/실험결과_*.md`, `docs/실패사례_*.md` | 1-7차 결과 문서 |
| `docs/오답노트.md` | 1-7차 실패 문항 분석(①-㊵)과 유형별 집계표 |
| `docs/Q4_테스트기록_전체.md` | Q4 한 문항을 1-5차에 걸쳐 따라간 기록 |
| `docs/번역검수표.csv` | 파일럿 23청크 사람 검수용 표(실록 사이트 링크, 확인 포인트) |
| `results/` | 원자료 JSONL 128개, 채점표 CSV 9개, 1차 자동 점검 합계(TSV), 검색 순위 진단(CSV) |
| `scripts/` | 채점 스크립트(`pilot_grades_20260928.py`, `grades_20260929_v2`-`v7.py`), 유형 집계(`wrongnote_tally.py`), 검색 순위 진단(`retrieval_rank_diag.py`) |

채점표 다시 만들기(저장소 맨 위에서):

```bash
python archive/파일럿_1-7차/scripts/grades_20260929_v5.py   # → archive/파일럿_1-7차/results/가채점표_…v5….csv
python archive/파일럿_1-7차/scripts/wrongnote_tally.py      # 오답노트 유형별 집계표
```

옮긴 뒤 다시 돌려서 채점표 9개와 집계표가 옮기기 전과 한 글자도 같은 것을 확인했습니다.

**파일럿 코퍼스와 평가셋**: 파일럿 23청크 코퍼스와 단발 평가셋(`single` 25문항, `holdout` 5문항), 옛 시나리오 파일은 새 코퍼스 연결(작업기록 [87]) 때 `data/`와 `data/eval/`로 옮겼습니다. 다회차 시나리오 A·B·C는 새 청크 번호와 날짜 시점으로 바꿔 평가셋 v3에 넣었습니다(`data/eval/v3_20260929_다회차_훈민정음.json`). `scripts/retrieval_rank_diag.py`는 지금 코드(793청크 코퍼스)를 불러오므로 파일럿 결과를 다시 만들지는 못합니다.

## 옛 경로 → 새 경로

작업기록의 지난 항목은 고치지 않으므로, 거기 적힌 옛 경로는 아래 표로 찾으면 됩니다.

| 옛 경로 | 새 경로 |
|---|---|
| `results/20260929-*` (새 코퍼스 1-4차, 84개) | `archive/새코퍼스_1-4차_793청크/results/` (파일 이름 그대로, 2026-09-30) |
| `data/청크/*_20260929_v1b*`, `data/청크/수동검사표_20260929_v1.csv`, `data/청크/청크비교_20260929_v1b_전략별통계.csv` | `archive/새코퍼스_1-4차_793청크/청크_v1b/` (2026-09-30) |
| `scripts/migrate_translations.py`, `scripts/remap_eval_chunks.py` | `archive/새코퍼스_1-4차_793청크/scripts/` (2026-09-30) |
| `docs/정제청킹_규칙서.md` (v1.1 본문 + v2 변경 10장) | `archive/새코퍼스_1-4차_793청크/정제청킹_규칙서_v1.1_와_v2변경.md`. `docs/정제청킹_규칙서.md`는 v2를 본문으로 새로 씀(2026-09-30) |
| `docs/데이터구축.md`, `docs/정제청킹_규칙서.md`, `docs/평가셋설계.md`, `docs/작업기록.md` | `docs/기록/데이터구축/`, `docs/기록/데이터가공/`(처음엔 `docs/기록/청크/`), `docs/기록/평가셋/`, `docs/기록/` (2026-10-01, 작업기록 [175]-[176]) |
| `docs/오답노트.md`, `docs/코퍼스.md`, `docs/기록/청크/` | `docs/기록/오답노트.md`, `docs/데이터.md`, `docs/기록/데이터가공/` (2026-10-01, [176]) |
| `results/20260930-20*`, `results/20260930-21*`, `results/20261001_search_answer_D2*` | `results/20260930_v2기준선/`, `results/20260930_검증셋v1/`, `results/20261001_검색보강답변평가/` (파일 이름 그대로, 2026-10-01, [177]) |
| `scripts/retrieval_embed_diag.py` (임베딩 small/large 진단, [96]) | `archive/새코퍼스_1-4차_793청크/scripts/` (2026-10-01, [178]) |
| `docs/중간점검_요청.md` | `archive/지난정리문서/중간점검_요청.md` (2단계 점검 완료, 보고서는 `docs/기록/전체검토/중간점검_20260929.md`, PR #29) |
| `docs/PILOT_RESULT_20260928.md` | `archive/파일럿_1-7차/docs/PILOT_RESULT_20260928.md` |
| `docs/EXPERIMENT.md` | `archive/파일럿_1-7차/docs/EXPERIMENT.md` |
| `docs/실험결과_20260929_v2`-`v7_*.md` | `archive/파일럿_1-7차/docs/` (파일 이름 그대로) |
| `docs/실패사례_20260929_v2_전제교정규칙_부작용.md` | `archive/파일럿_1-7차/docs/` |
| `docs/오답노트.md` (1-7차 내용) | `archive/파일럿_1-7차/docs/오답노트.md` (`docs/오답노트.md`는 새로 시작) |
| `results/*` | `archive/파일럿_1-7차/results/` (파일 이름 그대로) |
| `scripts/pilot_grades_20260928.py`, `scripts/grades_20260929_v*.py`, `scripts/wrongnote_tally.py`, `scripts/retrieval_rank_diag.py` | `archive/파일럿_1-7차/scripts/` |
| `docs/재개_20260929.md` | `HANDOFF.md` (`docs/현황.md`로 이름을 바꿔 내용을 갱신한 뒤, 저장소 맨 위로 옮김) |
| `docs/현황.md` | `HANDOFF.md` |
| `docs/스레드정리_20260929_확장번역·평가셋v2.md` | `archive/지난정리문서/` |
| `docs/참고/구조설명.md` | `archive/지난정리문서/` (`docs/구조.md`의 옛 사본) |
| `docs/참고/실록_RAG_작업재개_체크포인트.md` | `archive/지난정리문서/` (다른 AI에서 넘어올 때의 체크포인트) |
| `docs/평가셋설계_20260929_v2_한능검코퍼스.md`, `docs/평가셋설계_20260929_v3_함정보강.md` | `archive/평가셋_만든과정/docs/` (내용은 `docs/평가셋설계.md` 하나로 합침) |
| `data/eval/exam_20260929_v1.jsonl`, `data/eval/v2_20260929_한능검코퍼스.jsonl` | `archive/평가셋_만든과정/data/` (v3에 모두 들어 있음) |
| `scripts/build_eval_exam_v1_draft.py`, `scripts/build_eval_v2.py`, `scripts/build_eval_v3.py` | `archive/평가셋_만든과정/scripts/` |
| `docs/참고/Q4_테스트기록_전체.md`, `docs/참고/번역검수표.csv` | `archive/파일럿_1-7차/docs/` |
| `docs/참고/구조비교_법령챗봇.md` | `archive/지난정리문서/` |
| `docs/한능검_*_20260929.csv` (3개) | `data/한능검/` (파일 이름 그대로) |
| `docs/파일럿번역_수정제안_20260929.md` | `archive/파일럿_1-7차/docs/` (지적 29개를 새 번역 `data/번역_파일럿_20260929_v2.jsonl`에 모두 반영한 뒤) |
| `scripts/extract_expansion_articles.py`, 파일럿용 옛 `scripts/extract_articles.py` | `archive/기사목록_합치기전/scripts/` (파일럿용은 `extract_articles_파일럿7건.py`) |
| `data/expansion/후보기사목록_20260929.csv` | `data/기사목록.csv`(132건)로 합침, 옛 파일은 `archive/기사목록_합치기전/data/` |
| `data/expansion/articles_20260929.jsonl`, 파일럿 7건의 옛 `data/articles.jsonl` | `data/articles.jsonl`(132건)로 합침, 확장분 옛 파일은 `archive/기사목록_합치기전/data/` |
| `data/expansion/데이터표_20260929.csv` | `data/데이터표.csv`(132건)로 합침, 옛 파일은 `archive/기사목록_합치기전/data/` |
| `data/chunk_trial/*_20260929_v1_*` (수동검사표 제외 6개) | `archive/청크시험_v1_121건/` |
| `data/corpus.jsonl` (파일럿 23청크) | `archive/파일럿_1-7차/data/corpus.jsonl` (`data/corpus.jsonl`은 이제 132건 793청크) |
| `data/eval/single.jsonl`, `data/eval/holdout.jsonl`, `data/eval/scenarios.json` | `archive/파일럿_1-7차/data/eval/` (시나리오는 새 번호로 바꿔 `data/eval/v3_20260929_다회차_훈민정음.json`) |
| `scripts/build_expansion_corpus.py` | `scripts/build_corpus.py` (132건 전체 코퍼스를 만들도록 넓힘) |
| `data/chunk_trial/청크초안_20260929_v1b_132건_규칙서시험.jsonl` 등 `…_v1b_132건_…` 6개 | `data/청크/` (이름에서 `_132건_규칙서시험`·`_132건` 뺌, 예: `청크초안_20260929_v1b.jsonl`) |
| `data/chunk_trial/수동검사표_20260929_v1_규칙서시험.csv` | `data/청크/수동검사표_20260929_v1.csv` |
| `scripts/chunk_rules_trial.py` | `scripts/chunk_articles.py` |
| `data/expansion/번역_20260929_v1/001-012.jsonl` | `data/번역/001-012.jsonl` |
| `data/번역_파일럿_20260929_v2.jsonl` | `data/번역/013.jsonl` |
| `data/expansion/corpus_20260929_v1_규칙서.jsonl` (확장분만 769청크) | `archive/기사목록_합치기전/data/` (`data/corpus.jsonl`이 132건 793청크로 대신함) |
| `docs/확장분_번역코퍼스_20260929_v1.md` | `archive/기사목록_합치기전/` (내용은 `docs/코퍼스.md`로 새로 씀) |
| `docs/문서확장_한능검출제빈도_20260929.md` | `docs/데이터구축.md` (이름만 바꿈) |
| `data/청크/청크대응_20260930_v2.csv` | `archive/새코퍼스_1-4차_793청크/청크_v1b/` (v1b → v2 이사 때 한 번 쓴 대응표. 옛 결과의 청크 ID를 찾을 때만 씀, 작업기록 [137]) |
| `data/기사목록.csv` | `docs/기록/데이터구축/고른기사목록.csv` (이름 바꿈. ZIP에서 뽑을 때 한 번만 읽는 목록, 작업기록 [140]) |
| `data/청크/청크통계·정제기록·수동검사표_20260930_v2.csv` | `docs/기록/청크/` (코드가 읽지 않는 확인용 기록, [137]) |
| `docs/중간점검_20260929.md`, `docs/일일검토_20260930.md`, `docs/사람확인_남은항목_20260930.md`, `docs/원인분석_요청_20260930.md`, `docs/원인분석_20260930.md` | `docs/기록/전체검토/` (이름 그대로, [137]) |
| `scripts/answer_eval_budget.py`·`chunk_strategy_compare.py`·`chunk_strategy_retrieval.py`·`rerank_gloss_probe.py`·`speaker_label_sample.py`·`term_candidates.py`, `tests/test_answer_eval_budget.py` | `archive/scripts_20261008/` (끝난 실험 도구, 그 자리에서는 그대로 돌지 않음. 2026-10-08 코드 정리, 작업기록 [349]) |
| `data/eval/holdout_v2_claude_20261008.jsonl`, `data/eval/holdout_v2_openai_20261008.jsonl` | `docs/기록/평가셋/` (홀드아웃 v2 후보 두 판, 코드가 읽지 않는 기록. 2026-10-08, [349]) |
| `app.py`(10-13까지의 실험용 화면), `scripts/collect_deliverables.py`·`deliverables_stage4/5/6.py`·`office_export.py`·`final_slides.py`·`final_deck.js`·`record_demo_video.py` | `archive/scripts_20261014/` (옛 화면과 발표·제출 도구, 공개 준비 정리. 작업기록 [434]) |
| `docs/기록/코드정리검토_Claude·Codex·비교_20261008.md`, `docs/기록/다음테스트계획_20261002.md` | `archive/지난정리문서/` ([434]) |
