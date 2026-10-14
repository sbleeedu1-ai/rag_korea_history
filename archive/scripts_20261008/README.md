# 끝난 실험 스크립트 (2026-10-08 코드 정리)

한 번 쓰고 끝난 실험·조사 도구를 `scripts/`에서 옮겨 온 것입니다(코드정리검토 C9·X20-X22, 작업기록 [349]). 내용은 옮기기 전 그대로입니다.

| 파일 | 하던 일 | 결과·기록 |
|---|---|---|
| `answer_eval_budget.py`, `test_answer_eval_budget.py` | [161] 답변 평가의 범위·비용 점검과 예산 안 실행(옛 v4·low·top4 기준선·당시 단가 고정) | `results/20261001_*`, 작업기록 [161] |
| `chunk_strategy_compare.py` | 청킹 전략 3가지 통계 비교 | `archive/새코퍼스_1-4차_793청크/청크_v1b/청크비교_20260929_v1b_전략별통계.csv` |
| `chunk_strategy_retrieval.py` | 청킹 전략별 검색 성능 비교([217]) | `results/20261002_청킹전략검색/`, 규칙서 "검색 성능 비교" |
| `rerank_gloss_probe.py` | 리랭커 후보에 풀이를 붙이는 시험([303], 채택 안 함). **import만 해도 유료 호출로 들어가므로 실행하지 않음** | 작업기록 [303] |
| `speaker_label_sample.py` | 화자 라벨 표본 100개 뽑기([190]) | `docs/기록/데이터가공/화자라벨_표본검사_20261001.csv` |
| `term_candidates.py` | 번역문의 괄호 한자 낱말 후보 뽑기([208]) | `docs/기록/데이터가공/용어점검_후보_20261002.csv` |

**여기서는 그대로 돌지 않습니다.** 저장소 위치를 `scripts/` 기준(`parents[1]`, `scripts.` import)으로 찾고, `rerank_gloss_probe.py`는 걷어 낸 `RerankRetriever(gloss=…)`를 쓰며, `answer_eval_budget.py`는 옛 기준선(v4·top 4)을 전제로 합니다. 다시 쓰려면 태그 `freeze-20261007`(또는 커밋 `2ec4eab`)을 꺼내 그 시점 코드로 돌리고, 현행 문항·규칙·단가에 맞출지 먼저 정합니다. `test_answer_eval_budget.py`는 `pytest.ini`의 `testpaths = tests` 밖이라 테스트에 들어가지 않습니다.
