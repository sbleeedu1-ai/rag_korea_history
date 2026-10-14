"""실험 전체에서 공유하는 설정값."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CORPUS_PATH = DATA_DIR / "corpus.jsonl"
ARTICLES_PATH = DATA_DIR / "articles.jsonl"
EVAL_DIR = DATA_DIR / "eval"
# 평가셋 v3: 단발 67문항(jsonl)과 다회차 시나리오 A·B·C(json). 설계는 docs/데이터.md
EVAL_SET = "v3_20260929_한능검코퍼스+함정보강"
SCENARIOS_PATH = EVAL_DIR / "v3_20260929_다회차_훈민정음.json"
# 두 번째 사건(계유정난·사육신) 시나리오 D·E. 개발에 쓰지 않은 새 문항으로 ChatGPT와 같은 질문을 비교한다(작업기록 [188])
SCENARIOS_GYEYU_PATH = EVAL_DIR / "v4_20261001_다회차_계유정난.json"
CHROMA_DIR = ROOT / "chroma_db"   # 로컬 벡터 DB 폴더 (git에 올리지 않음)
RESULTS_DIR = ROOT / "results"

# 답변·리랭커 모델. 2026-09-29 gpt-4o-mini-2024-07-18 → gpt-6-luna(새 코퍼스 4차, 작업기록 [107][108]).
# gpt-6-luna는 날짜가 붙은 스냅샷 이름이 아직 없어(모델 목록 기준) 별칭으로 쓴다. 결과 파일에 모델 이름이 남는다.
ANSWER_MODEL = "gpt-6-luna"
ANSWER_EFFORT = "medium"   # 생각 수준. 4차: none 59/67, low 61/67. 2026-10-07 medium으로(작업기록 [305]-[309], 리랭커는 RERANK_EFFORT low 그대로)
RERANK_MODEL = ANSWER_MODEL
RERANK_EFFORT = "low"      # 4차: none 53/56, low 54/56(정답 청크 적중)
# LLM 자동 채점기. 전후 비교를 위해 당분간 이전 모델 그대로(교체는 재측정 계획에서 정함)
JUDGE_MODEL = "gpt-4o-mini-2024-07-18"
# 생각(추론) 단계가 있는 모델은 temperature를 받지 않고, 생각 수준(reasoning_effort)을 받는다.
# 2026-09-29 시험: gpt-6·gpt-5.6은 temperature를 거절(400), gpt-4o·gpt-4.1은 reasoning_effort를 거절(작업기록 [107]).
NO_TEMPERATURE_PREFIXES = ("gpt-6", "gpt-5.6")
REASONING_PREFIXES = ("gpt-6", "gpt-5", "o1", "o3", "o4")
EMBED_MODEL = "text-embedding-3-large"   # 2026-09-29 small → large (작업기록 [96], 검색 진단)
TEMPERATURE = 0
TOP_K = 6  # 2026-10-07 4 → 6(작업기록 [304]-[309])

# 결과 파일에 함께 기록해 어느 프롬프트로 돌린 결과인지 구분한다.
# 현행: 사실 질문 규칙 v9([230]-[232]), 역할 규칙 v8([211]-[212]). v9·v8 문장은 옛 규칙 문장을 바탕으로 고치거나 줄을 더한 것이다(prompts.py).
# v1-v8의 변천은 작업기록 [105]·[179]·[211]-[232]. 옛 규칙 선택지(--fact-rules v4/v8, --role-rules v7)는
# 2026-10-08 코드 정리 때 걷어 냄(코드정리검토 C6·X17). 옛 결과는 결과 파일에 남아 있다.
# 주의: [309]의 역할 규칙 한 줄 추가와 [313]의 리랭커 전제 판정 변경은 이 값을 바꾸지 않았다. 코드·커밋과 함께 확인한다.
PROMPT_VERSION = "v9"

# 새 코퍼스 2차: 리랭커. 검색기로 후보를 RERANK_CANDIDATES개 뽑고 답변 모델이 그중 top_k개를 고른다.
# 후보 20개: large 하이브리드에서 정답 청크가 20위 안에 드는 문항이 54/56(작업기록 [100]).
# 2026-09-29 기본값으로 켬(작업기록 [101]). 끄려면 CLI --no-rerank. 미리보기(dry-run)에서는 쓰지 않는다.
RERANK = True
RERANK_CANDIDATES = 20
# 2026-10-01: 리랭커 후보에 임베딩 상위 N개와 BM25 상위 N개(0점 제외)를 꼭 더한다(후보 평균 약 27개).
# 한쪽 검색기만 찾은 정답이 RRF에서 밀리던 문제(작업기록 [135], [143]). 0이면 예전처럼 합친 순위 20개만.
HYBRID_KEEP_EACH = 10
# 새 코퍼스 3차: 리랭커가 청크를 고르면서 질문 속 전제도 판정한다(호출 수 그대로).
RERANK_CHECK = True  # 2026-10-07 켬(gpt-6-luna로 판정 12개 중 10개 맞음, 작업기록 [304]-[309])
# 쉬운 말 풀이(gloss)를 검색에 쓰는 방식(작업기록 [286]·[297]·[302]).
# C안(2026-10-07 오후, 지금): 기존 BM25는 풀이 없이 두고, 풀이를 섞은 BM25를 따로 돌려 그 상위 GLOSS_KEEP개를 리랭커 후보에 보탠다
#   (각 검색기 상위 보태기와 같은 원리). 무료 모의실험에서 후보 안 정답 94/94(기존 BM25에 풀이를 섞은 B안 93), 후보 평균 26.1 → 26.3개.
#   결과 파일의 검색기 이름에 '-glosskeep5'가 붙는다. 끄려면 GLOSS_KEEP = 0.
# 채택하지 않은 시험 옵션(B안 토글 BM25_GLOSS, 리랭커 후보에 풀이 붙이기 RERANK_GLOSS [303], 앞 청크 붙이기 PREV_CHUNK [304])은
# 2026-10-08 코드 정리 때 걷어 냄(코드정리검토 C3-C5·X18). 코드는 git 이력(태그 freeze-20261007)에 있다.
BM25_GLOSS_WEIGHT = 0.5
GLOSS_KEEP = 5

# 파일럿의 조건 A(원문 전체)·B(번역문 전체)는 793청크에서 모델 입력 한도를 넘어 2026-09-29 정리 때 지움(작업기록 [105])
CONDITIONS = {
    "C": "번역문을 DB에서 검색해 제공",
    "D1": "C + 장면 시점 필터",
    "D2": "D1 + 해설자 대화 이력 분리",
}
