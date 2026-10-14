"""실록 RAG 실험용 Streamlit 화면.

실행: streamlit run app.py
OpenAI 키는 프로젝트 폴더의 .env 파일(OPENAI_API_KEY=...)에 넣는다. 키가 없으면 미리보기(dry-run)로 동작한다.
"""
import json
import os

import streamlit as st

from sillok_rag import config
from sillok_rag.chat import ChatSession
from sillok_rag.corpus import cite, load_chunks, read_jsonl, sillok_url
from sillok_rag.evaluate import load_all_scenarios, result_files, summarize
from sillok_rag.llm import LLM
from sillok_rag.retrieval import BM25Retriever, ChromaRetriever, HybridRetriever, RerankRetriever, gloss_extra
from sillok_rag.store import chroma_matches, chroma_ready

st.set_page_config(page_title="실록 인터뷰 RAG 실험", page_icon="📜", layout="wide")
SCREEN_CONDITIONS = list(config.CONDITIONS)   # C·D1·D2
EMPTY_ANSWER = "(모델이 빈 답을 돌려줬습니다. 다시 물어 보세요.)"   # llm.chat이 None 대신 빈 답을 줌(코드정리검토 C1)


def api_key() -> str | None:
    # sillok_rag.llm 을 import할 때 .env 를 이미 읽어 둔다
    return os.environ.get("OPENAI_API_KEY")


@st.cache_data
def chunks_cached():
    return load_chunks()


chunks = chunks_cached()
by_id = {c["chunk_id"]: c for c in chunks}
scenarios = load_all_scenarios()   # A·B·C 훈민정음, D·E 계유정난·사육신
key = api_key()

# ---------- 사이드바: 실험 조건 ----------
with st.sidebar:
    st.header("실험 조건")
    dry_run = st.toggle("미리보기(API 호출 안 함)", value=key is None, disabled=key is None,
                        help="키가 없으면 프롬프트와 검색 결과만 확인합니다.")
    if key is None:
        st.info(".env에 OPENAI_API_KEY가 없어 미리보기로 동작합니다.")
    condition = st.radio("조건", SCREEN_CONDITIONS,
                         format_func=lambda c: f"{c} · {config.CONDITIONS[c]}", index=len(SCREEN_CONDITIONS) - 1)
    db_ok = chroma_ready() and chroma_matches(chunks)
    if chroma_ready() and not db_ok:
        st.warning("Chroma DB가 지금 코퍼스와 다릅니다. `python -m sillok_rag.cli build-db`로 다시 만들 때까지 BM25만 씁니다.")
    options = ["bm25"] + (["chroma", "hybrid"] if db_ok and not dry_run else [])
    retriever_kind = st.radio("검색기 (C·D)", options, index=len(options) - 1,
                              help="chroma·hybrid는 `python -m sillok_rag.cli build-db` 후 사용 가능. "
                                   "hybrid(임베딩+BM25)가 4차 실험에서 채택한 기본값. 키가 있으면 리랭커가 후보 약 26개 중 6개를 고르고 질문 속 전제도 판정함(새 코퍼스 2·3차)")
    mode = st.radio("대화 방식", ["사실 질문", "인물 인터뷰"])
    scene_id = None
    if mode == "인물 인터뷰":
        scene_id = st.selectbox("장면", list(scenarios), format_func=lambda s: f"{s} · {scenarios[s]['title']}")
        st.caption(scenarios[scene_id]["setup"])
    want_evidence = st.toggle("근거 보기 만들기", value=False, disabled=dry_run,
                              help="답변마다 모델 호출 1번을 더 해서 문장별 실록 기록/실록 풀이/인물 시점/AI 창작과 근거 기사를 붙입니다(작업기록 [196]).")
    st.caption(f"답변·리랭커 모델: `{config.ANSWER_MODEL}` · 생각 수준 {config.ANSWER_EFFORT}")


def make_llm():
    return LLM(dry_run=dry_run, api_key=key)


def make_retriever(llm):
    if retriever_kind == "hybrid":
        base = HybridRetriever(ChromaRetriever(chunks, llm), BM25Retriever(chunks), keep_each=config.HYBRID_KEEP_EACH,
                               extra=gloss_extra(chunks))
    elif retriever_kind == "chroma":
        base = ChromaRetriever(chunks, llm)
    else:
        base = BM25Retriever(chunks)
    # 리랭커(새 코퍼스 2차): 후보 20개 중 모델이 top_k개를 고른다. 미리보기에서는 쓰지 않는다
    # 리랭커는 답변과 생각 수준이 다를 수 있어 따로 만든다(답변 medium, 리랭커 low, 작업기록 [309]). 전제 판정도 config 그대로
    rerank_llm = llm if config.RERANK_EFFORT == config.ANSWER_EFFORT else \
        LLM(dry_run=dry_run, api_key=key, reasoning_effort=config.RERANK_EFFORT)
    return RerankRetriever(base, rerank_llm, config.RERANK_CANDIDATES, check=config.RERANK_CHECK) if config.RERANK and not dry_run else base


def new_session(cond: str) -> ChatSession:
    llm = make_llm()
    sc = scenarios[scene_id] if scene_id else None
    return ChatSession(cond, chunks, llm, make_retriever(llm),
                       mode="role" if sc else "fact",
                       character=sc and sc["character"], setting=sc and sc["setup"],
                       cutoff=sc and sc["cutoff"], known_facts=sc and sc.get("known_facts"))


def show_sources(context_ids: list[str], retrieved: list[dict]):
    scores = {r["chunk_id"]: r["score"] for r in retrieved}
    # 검색된 자료 목록(실험용). 답을 실제로 뒷받침하는 근거는 show_evidence가 따로 보여 준다(화면 기획 8장)
    label = "검색된 자료 (전체 자료 제공)" if len(context_ids) == len(chunks) else f"검색된 자료 ({len(context_ids)}개 청크)"
    with st.expander(label):
        for cid in context_ids:
            c = by_id[cid]
            score = f" · 점수 {scores[cid]}" if cid in scores else ""
            st.markdown(f"**{cid}** · [{cite(c)}]({sillok_url(c['article_id'])}) · 화자 {c['speaker']} · "
                        f"알려진 시점 {c['known_from']}{score}")
            st.markdown(f"> {c['original']}")
            st.write(c["translation"])


# 화면 이름은 [205] 사용자 결정. 내부 표시 이름(기록·해석·시점·창작)은 저장 결과와 맞추려고 그대로 둔다
LABEL_STYLE = {"기록": "🟩 실록 기록", "해석": "🟨 실록 풀이", "시점": "🟦 인물 시점", "창작": "⬜ AI 창작"}


def show_evidence(ev: dict | None):
    """근거 보기: 실록 기록 문장이 있을 때만 버튼(펼치기)을 보인다. 기사 카드에 원문·우리 번역·강조 구절·화자."""
    if not ev or not ev.get("show_button"):
        return
    with st.expander("📑 근거 보기"):
        for s in ev["segments"]:
            src = f" · {s['source']}" if s["label"] == "기록" and s["source"] else ""
            st.markdown(f"{LABEL_STYLE[s['label']]}{src} — {s['text']}")
        st.divider()
        for card in ev["cards"]:
            st.markdown(f"**{card['title']}** · {card['record_date'] or '총서'} · [{card['cite']}]({card['url']}) · 화자 {card['speaker']}")
            st.markdown(f"> {card['original']}")
            text = card["translation"]
            for q in card["quotes"]:
                text = text.replace(q, f"**{q}**")
            st.markdown(text)


tab_chat, tab_compare, tab_results, tab_data = st.tabs(["대화", "조건 비교", "실험 결과", "자료 보기"])

# ---------- 대화 ----------
with tab_chat:
    settings = (condition, retriever_kind, mode, scene_id, dry_run)
    if st.session_state.get("settings") != settings or st.button("대화 새로 시작"):
        st.session_state.settings = settings
        st.session_state.session = new_session(condition)
        if scene_id:
            st.session_state.session.ask(scenarios[scene_id]["setup"])
    session: ChatSession = st.session_state.session

    st.caption("인물 인터뷰는 설정 문구가 첫 메시지로 들어갑니다. "
               "D2에서는 '역할을 벗고', '실제 역사' 같은 요청을 해설자가 따로 답합니다.")
    for t in session.log:
        with st.chat_message("user"):
            st.write(t.user)
        name = {"character": session.character, "narrator": "해설자", "assistant": "도우미"}[t.speaker]
        with st.chat_message("assistant", avatar="🧑‍🏫" if t.speaker == "narrator" else "📜"):
            st.markdown(f"**{name}**")
            st.write(t.answer or EMPTY_ANSWER)
            show_evidence(t.evidence)
            show_sources(t.context_ids, t.retrieved)

    if prompt := st.chat_input("질문을 입력하세요"):
        session.ask(prompt)
        if want_evidence and not dry_run:
            session.evidence_for(len(session.log) - 1)
        st.rerun()

# ---------- 조건 비교 ----------
with tab_compare:
    st.write("같은 질문을 조건 C·D1·D2에 한 번씩 보내 나란히 봅니다. 각 조건은 새 대화(이력 없음)로 실행합니다.")
    q = st.text_input("질문", value="김문은 결국 어떤 처벌을 받았는가?")
    if st.button("세 조건으로 실행", disabled=not q):
        cols = st.columns(len(SCREEN_CONDITIONS))
        for col, cond in zip(cols, SCREEN_CONDITIONS):
            s = new_session(cond)
            if scene_id:
                s.ask(scenarios[scene_id]["setup"])
            t = s.ask(q)
            with col:
                st.subheader(cond)
                st.caption(config.CONDITIONS[cond])
                st.write(t.answer or EMPTY_ANSWER)
                show_sources(t.context_ids, t.retrieved)

# ---------- 실험 결과 ----------
with tab_results:
    files = result_files(config.RESULTS_DIR)   # 채점 결과(.llmgrade.jsonl)는 뺀다
    if not files:
        st.info("아직 결과 파일이 없습니다. `python -m sillok_rag.cli run-all` 로 실험을 실행하세요.")
    else:
        picked = st.multiselect("결과 파일", files, default=files[:1],
                                format_func=lambda p: p.relative_to(config.RESULTS_DIR).as_posix())
        if picked:
            st.dataframe(summarize(picked), width="stretch")
            st.caption("자동 점검은 힌트입니다. 최종 판정은 grade-sheet로 만든 CSV에 기록하세요.")
            for p in picked:
                with st.expander(p.name):
                    for r in read_jsonl(p):
                        st.markdown(f"**{r['qid']}** ({r['category']}) {r['question']}")
                        st.write(r["answer"])
                        st.caption(f"기대: {r['expected']} · 자동 점검: {json.dumps(r['auto'], ensure_ascii=False)}")

# ---------- 자료 보기 ----------
with tab_data:
    st.write(f"청크 {len(chunks)}개. 번역은 AI 초안 번역을 사람이 검수한 것입니다(규칙서 v2, 쉬운 말 풀이는 사전 대조·사용자 검수).")
    st.dataframe(
        [{"청크": c["chunk_id"], "출처": cite(c), "화자": c["speaker"], "알려진 시점": c["known_from"],
          "번역": c["translation"], "원문": c["original"]} for c in chunks],
        width="stretch", hide_index=True,
    )
