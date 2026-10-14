"""시연 화면과 기존 D2 실행 경로를 잇는다. 화면을 여는 것만으로 API를 부르지 않는다."""
import os

from ui import episode, fast_trial
from sillok_rag import config
from sillok_rag.chat import ChatSession, TurnResult
from sillok_rag.cli import make_retriever
from sillok_rag.llm import LLM
from sillok_rag.retrieval import BM25Retriever, ChromaRetriever, HybridRetriever, RerankRetriever, gloss_extra
from sillok_rag.store import chroma_matches, chroma_ready

# 설정 창에 보이는 실행 설정. 시험 모드(SILLOK_FAST=1)면 측정 설정과 다르다고 밝힌다
SETTINGS_LABEL = fast_trial.LABEL if fast_trial.ON else "측정 설정: D2 · 답변 medium · 리랭커 low · 자료 6개"


LIVE_RETRIEVER = "hybrid-avgtie-keep10-date-glosskeep5_rerank20_check"
FACT_QUESTIONS = (
    "《삼강행실도》를 처음 엮을 때 효자·충신·열녀의 사례는 각각 몇 명씩 골랐어?",
    "숙종 때 금위영에 대장을 따로 두기로 했다던데, 그때 대장으로 누구를 임명했어?",
    "조선 통신사 기록물이 유네스코 세계기록유산에 등재된 해는 언제야?",
)


def api_key() -> str:
    """빈 값과 공백만 있는 환경 변수도 키 없음으로 다룬다."""
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def live_problem(chunks: list[dict]) -> str | None:
    """유료 호출 전에 키와 동결 코퍼스의 DB를 확인한다."""
    if not api_key():
        return "이 작업 폴더의 .env에 OPENAI_API_KEY를 설정해 주세요."
    try:
        if not chroma_ready():
            return "이 작업 폴더에 검색 DB가 없습니다."
        if not chroma_matches(chunks):
            return "검색 DB와 현재 실록 자료가 일치하지 않습니다."
    except Exception:
        return "검색 DB를 읽지 못했습니다. 파일과 실행 환경을 확인해 주세요."
    return None


def _models(chunks, preview, answer_llm, rerank_llm):
    """실제 실행이면 키·DB를 먼저 확인하고, 측정 설정(답변 medium·리랭커 low)으로 모델을 만든다."""
    if not preview:
        problem = live_problem(chunks)
        if problem:
            raise RuntimeError(problem)
    answer_llm = answer_llm or LLM(dry_run=preview, api_key=api_key(),
                                   reasoning_effort=config.ANSWER_EFFORT)
    rerank_llm = rerank_llm or LLM(model=config.RERANK_MODEL, dry_run=preview, api_key=api_key(),
                                  reasoning_effort=fast_trial.RERANK_EFFORT if fast_trial.ON else config.RERANK_EFFORT)
    return answer_llm, rerank_llm


def create_session(chunks, scene=None, *, preview=True, answer_llm=None, rerank_llm=None):
    """CLI와 같은 검색기 조립 및 설정(실록 자료실과 동일성 검사에서 씀). 가짜 모델 주입은 무료 연결 검사에 쓴다."""
    answer_llm, rerank_llm = _models(chunks, preview, answer_llm, rerank_llm)
    try:
        retriever = make_retriever("bm25" if preview else "hybrid", chunks, answer_llm,
                                   rerank=True, check=True, rerank_llm=rerank_llm)
    except SystemExit as exc:
        # CLI의 종료 안내를 웹 앱 전체 종료로 전달하지 않는다.
        raise RuntimeError("검색 DB를 확인한 뒤 다시 보내 주세요.") from exc
    if not preview and retriever.name != LIVE_RETRIEVER:
        raise RuntimeError("발표에서 측정한 검색 설정과 다릅니다. 실행 설정을 확인해 주세요.")
    return ChatSession("D2", chunks, answer_llm, retriever, mode="role" if scene else "fact",
                       character=scene and scene["character"], setting=scene and scene["setup"],
                       cutoff=scene and scene["cutoff"], known_facts=scene and scene.get("known_facts"),
                       top_k=config.TOP_K)


class AllowedDense:
    """임베딩 검색 결과를 허용 청크로만 거른다(인물이 쓸 수 있는 자료 제한, 엔진은 그대로)."""
    name = "chroma"

    def __init__(self, inner, allowed):
        self.inner, self.allowed = inner, set(allowed)

    def search(self, query, k, max_known=None, scene=None):
        hits = self.inner.search(query, len(self.inner.by_id), max_known, **({"scene": scene} if scene else {}))
        return [hit for hit in hits if hit[0]["chunk_id"] in self.allowed][:k]


def episode_retriever(chunks, allowed, answer_llm, rerank_llm, preview):
    """cli.make_retriever와 같은 조립(하이브리드 + 풀이 BM25 후보 + 리랭커·전제 판정)을 허용 청크에만 적용한다."""
    allowed = set(allowed)
    subset = [c for c in chunks if c["chunk_id"] in allowed]
    if preview:
        return subset, BM25Retriever(subset)
    dense = AllowedDense(ChromaRetriever(chunks, answer_llm), allowed)
    base = HybridRetriever(dense, BM25Retriever(subset), keep_each=config.HYBRID_KEEP_EACH,
                           extra=gloss_extra(subset))
    retriever = RerankRetriever(base, rerank_llm, config.RERANK_CANDIDATES, check=True)
    if retriever.name != LIVE_RETRIEVER:
        raise RuntimeError("발표에서 측정한 검색 설정과 다릅니다. 실행 설정을 확인해 주세요.")
    return subset, retriever


def open_interview(chunks, who, *, preview=True, answer_llm=None, rerank_llm=None, ep=episode):
    """면담 하나(ep = 사건 데이터 모듈). 인물은 고정 시점의 역할 대화, 해설자는 사실 질문 규칙으로 답한다."""
    answer_llm, rerank_llm = _models(chunks, preview, answer_llm, rerank_llm)
    person = ep.PEOPLE.get(who)
    allowed = person["allowed"] if person else ep.NARRATOR_IDS
    subset, retriever = episode_retriever(chunks, allowed, answer_llm, rerank_llm, preview)
    if not person:
        return ChatSession("D2", subset, answer_llm, retriever, mode="fact", top_k=config.TOP_K)
    session = ChatSession("D2", subset, answer_llm, retriever, mode="role", character=who,
                          setting=person["setup"], cutoff=person["cutoff"],
                          known_facts=person["known_facts"], top_k=config.TOP_K)
    # 측정 때처럼 설정 문장을 첫 질문으로 두되, 첫 답은 미리 쓴 인사로 넣어 호출을 줄인다(대화 이력은 log로 만들어짐)
    session.log.append(TurnResult(person["setup"], person["greeting"], "character", [], []))
    return session


def ask_nonempty(session, question):
    """엔진 로그를 보존하면서 빈 답을 화면의 재시도 안내로 전달한다."""
    turn = session.ask(question)
    if not turn.answer or not turn.answer.strip():
        raise RuntimeError("빈 답변")
    return turn


def submit(session, question, scene=None):
    """장면 설정은 CLI의 첫 턴과 같은 문장으로 한 번만 보낸다(실록 자료실·동일성 검사용)."""
    if scene and not session.log:
        ask_nonempty(session, scene["setup"])
    return ask_nonempty(session, question)


def ask_and_check(session, question, preview):
    """답을 받고, 실제 실행이면 바로 근거 판정을 붙인다(목표 체크·근거 보기 창에 씀, 호출 1번 추가)."""
    turn = ask_nonempty(session, question)
    if not preview:
        request_evidence(session, len(session.log) - 1)
    return turn


def request_evidence(session, index):
    """성공한 근거는 다시 펼쳐도 재호출하지 않는다. 실패한 경우에만 재시도한다."""
    previous = session.log[index].evidence
    if previous is not None and not previous.get("error"):
        return previous
    return fast_trial.evidence_for(session, index) if fast_trial.ON else session.evidence_for(index)


def goal_parts(evidence, goals=None) -> dict:
    """근거 판정에서 목표의 작은 항목을 찾는다: 확인된 실록 기록 문장이 목표 청크를 가리키고 구절에 핵심 말이 있을 때.
    돌려주는 값은 {항목: (근거 청크, 답 문장)}. 질문 문장이나 버튼 클릭은 보지 않는다."""
    found = {}
    for seg in (evidence or {}).get("segments", []):
        if seg.get("label") != "기록" or not seg.get("verified"):
            continue
        for goal in (goals or episode.GOALS).values():
            for part, sources in goal["parts"].items():
                words = sources.get(seg.get("source"))
                if words is not None and (not words or any(w in seg.get("quote", "") for w in words)):
                    found.setdefault(part, (seg["source"], seg["text"]))
    return found


def goals_done(parts: dict, goals=None) -> dict:
    """큰 줄기별 확인 여부. 줄기 안의 작은 항목이 모두 확인돼야 한다(③은 셋 다)."""
    return {gid: all(part in parts for part in goal["parts"]) for gid, goal in (goals or episode.GOALS).items()}
