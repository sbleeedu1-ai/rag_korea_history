import hashlib

import pytest

from sillok_rag import config

from sillok_rag.chat import ChatSession, is_out_of_role
from sillok_rag.corpus import known_key, load_chunks
from sillok_rag.evaluate import fabricated_quotes, load_scenarios
from sillok_rag.retrieval import BM25Retriever, HybridRetriever

chunks = load_chunks()
key = {c["chunk_id"]: c["known_key"] for c in chunks}
PETITION = "wda_12602020_001"
KIM_MUN_PUNISHED = "wda_12602021_001-01"   # 의금부 탄핵과 김문의 속장


def allowed(cid, cutoff):
    return key[cid] is not None and key[cid] <= known_key(cutoff)


class FakeLLM:
    model = "fake"
    dry_run = True
    embed_model = "fake-embed"

    def __init__(self):
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return f"답변{len(self.calls)}"

    def embed(self, texts):
        # 글자 해시로 만든 가짜 벡터. Chroma 필터 동작만 확인한다.
        out = []
        for t in texts:
            v = [0.0] * 64
            for ch in t:
                v[int(hashlib.md5(ch.encode()).hexdigest(), 16) % 64] += 1
            out.append(v)
        return out


def test_bm25_finds_kim_mun_punishment():
    # 793청크에서는 "결국 어떤 처벌을 받았는가?"처럼 흔한 낱말이 많으면 다른 기사의 '처벌' 청크가 앞선다(13위, 작업기록 [87]).
    hits = BM25Retriever(chunks).search("김문은 어떤 벌을 받았나", 4)
    assert KIM_MUN_PUNISHED in [c["chunk_id"] for c, _ in hits]


def test_bm25_indexes_record_date_for_year_questions():
    """검색 본문에 날짜가 없어 연도로 묻는 F43이 454위였다. BM25 색인에만 기록일·재위년을 넣는다(작업기록 [183])."""
    from sillok_rag.retrieval import date_text

    c = next(c for c in chunks if c["chunk_id"] == "wga_11208025_005-01")
    assert date_text(c) == "1466년 8월 25일 세조 12년"
    assert date_text({"record_date": None, "reign": "태조 총서"}) == "태조 총서"
    hits = BM25Retriever(chunks).search("1466년 세조 때 토지 제도는 어떻게 바뀌었나?", 4)
    assert hits[0][0]["chunk_id"] == "wga_11208025_005-01"


def test_time_filter_drops_future_chunks():
    cut = known_key("1444-02-20")
    hits = BM25Retriever(chunks).search("내일 석방 파직 반포 해례", 10, max_known=cut)
    assert hits and all(c["known_key"] is not None and c["known_key"] <= cut for c, _ in hits)
    # 사론·졸기('후일 기록')는 어떤 장면에서도 빠진다
    assert all(c["known_key"] is not None for c, _ in BM25Retriever(chunks).search("사신은 논한다", 50, max_known=cut))


def test_chroma_where_filter(tmp_path):
    from sillok_rag.retrieval import ChromaRetriever
    from sillok_rag.store import build_chroma, open_collection

    llm = FakeLLM()
    build_chroma(llm, persist_dir=tmp_path, chunks=chunks)
    r = ChromaRetriever(chunks, llm, collection=open_collection(tmp_path))
    cut = known_key("1444-02-20 오후")
    hits = r.search("이튿날 석방", 5, max_known=cut)
    assert len(hits) == 5 and all(c["known_key"] is not None and c["known_key"] <= cut for c, _ in hits)


class FakeEmbedder(FakeLLM):
    """지금 설정의 임베딩 모델 이름을 쓰는 가짜(DB 일치 검사는 모델 이름도 본다)."""
    embed_model = config.EMBED_MODEL


def test_chroma_matches_only_the_corpus_it_was_built_from(tmp_path):
    """청크·번역·시점이 바뀐 뒤 DB를 다시 만들지 않으면 옛 본문으로 검색하게 된다(2026-09-30 일일 검토: 793 DB와 803 코퍼스)."""
    from sillok_rag.store import build_chroma, chroma_matches

    small = chunks[:30]
    build_chroma(FakeEmbedder(), persist_dir=tmp_path, chunks=small)
    assert chroma_matches(small, persist_dir=tmp_path)
    changed = [dict(c) for c in small]
    changed[0]["translation"] += " (고침)"
    assert not chroma_matches(changed, persist_dir=tmp_path)
    moved = [dict(c) for c in small]
    moved[1]["known_key"] = None   # 시점만 바뀌어도 다르다
    assert not chroma_matches(moved, persist_dir=tmp_path)
    assert not chroma_matches(small, persist_dir=tmp_path / "없음")


def test_chroma_matches_checks_model_and_count(tmp_path):
    """지문이 같아도 다른 임베딩 모델로 만들었거나 일부만 들어간 DB는 다르다(전체검토 2-8 6번)."""
    from sillok_rag.store import COLLECTION, _client, build_chroma, chroma_matches

    small = chunks[:30]
    build_chroma(FakeLLM(), persist_dir=tmp_path / "다른모델", chunks=small)   # embed_model = fake-embed
    assert not chroma_matches(small, persist_dir=tmp_path / "다른모델")
    build_chroma(FakeEmbedder(), persist_dir=tmp_path / "일부", chunks=small)
    _client(tmp_path / "일부").get_collection(COLLECTION).delete(ids=[small[0]["chunk_id"]])
    assert not chroma_matches(small, persist_dir=tmp_path / "일부")


class _FailingEmbed(FakeEmbedder):
    def embed(self, texts):
        raise ConnectionError("임베딩 API 실패")


class _ShortEmbed(FakeEmbedder):
    def embed(self, texts):
        return super().embed(texts)[:-1]


def test_failed_rebuild_keeps_existing_db(tmp_path):
    """다시 만들다 임베딩이나 저장이 실패해도 기존 DB가 그대로 남는다(전체검토 2-8 1번)."""
    from sillok_rag.store import COLLECTION, _client, build_chroma, chroma_matches

    old, new = chunks[:30], [dict(c) for c in chunks[:30]]
    new[0]["translation"] += " (고침)"
    build_chroma(FakeEmbedder(), persist_dir=tmp_path, chunks=old)
    with pytest.raises(ConnectionError):
        build_chroma(_FailingEmbed(), persist_dir=tmp_path, chunks=new)
    assert chroma_matches(old, persist_dir=tmp_path)
    with pytest.raises(RuntimeError, match="그대로"):
        build_chroma(_ShortEmbed(), persist_dir=tmp_path, chunks=new)
    assert chroma_matches(old, persist_dir=tmp_path)
    class _BrokenAdd(FakeEmbedder):
        pass

    import chromadb.api.models.Collection as collection_module
    original_add = collection_module.Collection.add

    def broken_add(self, *args, **kwargs):
        raise ValueError("저장 실패")

    collection_module.Collection.add = broken_add
    try:
        with pytest.raises(ValueError):
            build_chroma(_BrokenAdd(), persist_dir=tmp_path, chunks=new)
    finally:
        collection_module.Collection.add = original_add
    assert chroma_matches(old, persist_dir=tmp_path)
    assert [c.name for c in _client(tmp_path).list_collections()] == [COLLECTION]   # 임시 컬렉션도 안 남음
    build_chroma(FakeEmbedder(), persist_dir=tmp_path, chunks=new)                  # 성공하면 새 DB로 바뀜
    assert chroma_matches(new, persist_dir=tmp_path) and not chroma_matches(old, persist_dir=tmp_path)


def test_failed_final_rename_keeps_existing_db(tmp_path, monkeypatch):
    """새 DB를 다 만든 뒤 마지막 이름 바꾸기가 실패해도 기존 DB가 원래 이름으로 남는다(코드정리검토 X1·C21).
    교체가 중간에 멈춰 옛 DB만 '_old'로 남았으면 다음 build-db가 정리한다."""
    import chromadb.api.models.Collection as collection_module

    from sillok_rag.store import COLLECTION, _client, build_chroma, chroma_matches

    old, new = chunks[:30], [dict(c) for c in chunks[:30]]
    new[0]["translation"] += " (고침)"
    build_chroma(FakeEmbedder(), persist_dir=tmp_path, chunks=old)
    original_modify = collection_module.Collection.modify

    def broken_modify(self, *args, **kwargs):
        if self.name == COLLECTION + "_new":
            raise OSError("이름 바꾸기 실패")
        return original_modify(self, *args, **kwargs)

    monkeypatch.setattr(collection_module.Collection, "modify", broken_modify)
    with pytest.raises(OSError):
        build_chroma(FakeEmbedder(), persist_dir=tmp_path, chunks=new)
    monkeypatch.setattr(collection_module.Collection, "modify", original_modify)
    assert chroma_matches(old, persist_dir=tmp_path)
    # 교체 도중 멈춘 상태(정상 이름 없이 '_old'만)를 만들어도 다음 실행이 정리하고 새 DB로 바꾼다
    _client(tmp_path).get_collection(COLLECTION).modify(name=COLLECTION + "_old")
    build_chroma(FakeEmbedder(), persist_dir=tmp_path, chunks=new)
    assert chroma_matches(new, persist_dir=tmp_path)
    assert [c.name for c in _client(tmp_path).list_collections()] == [COLLECTION]


def test_d1_role_context_respects_cutoff_but_c_does_not_filter():
    sc = load_scenarios()["A"]
    for cond, expect_filtered in (("C", False), ("D1", True)):
        s = ChatSession(cond, chunks, FakeLLM(), BM25Retriever(chunks), mode="role",
                        character=sc["character"], setting=sc["setup"], cutoff=sc["cutoff"], top_k=30)
        t = s.ask("영감께서는 내일 석방되십니까?")
        filtered = all(allowed(cid, sc["cutoff"]) for cid in t.context_ids)
        assert filtered == expect_filtered


class _SceneSpy:
    """검색기에 넘어온 장면 설정을 기록하는 가짜 검색기."""
    def __init__(self):
        self.calls = []

    def search(self, query, k, max_known=None, scene=None):
        self.calls.append((query, scene))
        return [(c, 1.0) for c in chunks[:k]]


def test_role_turns_pass_scene_to_retriever_but_not_narrator_or_fact():
    """인물이 답하는 턴만 장면 설정을 검색에 함께 준다. 이번 질문은 그대로이고 앞선 대화는 넣지 않는다(작업기록 [183])."""
    sc = load_scenarios()["B"]
    spy = _SceneSpy()
    s = ChatSession("D2", chunks, FakeLLM(), spy, mode="role", character=sc["character"],
                    setting=sc["setup"], cutoff=sc["cutoff"])
    b1, b5 = sc["turns"][0]["user"], sc["turns"][4]["user"]
    t1, t5 = s.ask(b1), s.ask(b5)
    assert spy.calls[0] == (b1, sc["setup"]) and t1.search_scene
    assert spy.calls[1] == (b5, None) and not t5.search_scene        # 해설자 턴
    spy = _SceneSpy()
    ChatSession("D2", chunks, FakeLLM(), spy).ask("1466년 토지 제도는?")
    assert spy.calls == [("1466년 토지 제도는?", None)]


def test_hybrid_gives_scene_only_to_dense_and_reranker_sees_it():
    """장면 문장은 임베딩 검색어에만 붙인다. BM25에도 붙이면 C6의 다른 기사가 후보에서 빠졌다([183] 진단)."""
    from sillok_rag.prompts import rerank_messages
    from sillok_rag.retrieval import RerankRetriever

    dense, sparse = _SceneSpy(), _SceneSpy()
    sparse.chunks = chunks
    hy = HybridRetriever(dense, sparse, keep_each=2)
    hy.n = 5
    hy.candidates("상소를 올리신 까닭은?", 3, None, scene="최만리 장면")
    assert dense.calls == [("상소를 올리신 까닭은?", "최만리 장면")]
    assert sparse.calls == [("상소를 올리신 까닭은?", None)]
    llm = PickLLM('{"ids": []}')
    RerankRetriever(hy, llm, 3).search("상소를 올리신 까닭은?", 2, None, scene="최만리 장면")
    user = llm.calls[0][1]["content"]
    assert user.startswith("[장면") and "최만리 장면" in user and "[질문]\n상소를 올리신 까닭은?" in user
    assert not rerank_messages("질문", chunks[:2], 1)[1]["content"].startswith("[장면")


def test_d2_keeps_narrator_answer_out_of_character_history():
    sc = load_scenarios()["B"]
    turns = [t["user"] for t in sc["turns"]]
    b5, b6 = turns[4], turns[5]
    assert is_out_of_role(b5) and not is_out_of_role(b6)

    for cond in ("D1", "D2"):
        llm = FakeLLM()
        s = ChatSession(cond, chunks, llm, BM25Retriever(chunks), mode="role",
                        character=sc["character"], setting=sc["setup"], cutoff=sc["cutoff"])
        for u in turns[:6]:
            s.ask(u)
        b6_messages = llm.calls[5]
        seen = [m["content"] for m in b6_messages]
        if cond == "D2":
            assert s.log[4].speaker == "narrator"
            assert b5 not in seen and "답변5" not in seen
            # 해설자는 시점 필터 없이 검색한다
            assert "[해설자]" in llm.calls[4][0]["content"]
        else:
            assert b5 in seen and "답변5" in seen


def test_fabricated_quote_detection():
    ok = "상소에 「二十七字諺文, 足以立身於世」라고 했습니다."
    bad = "상소에 「今新制諺文，不過二十八字」라고 했습니다."
    assert fabricated_quotes(ok, chunks) == []
    assert fabricated_quotes(bad, chunks) == ["今新制諺文", "不過二十八字"]


def test_known_facts_always_in_role_prompt_even_with_cutoff():
    """시점 필터(D1)가 하옥 청크(-14, 같은 날 오후)를 빼도 '아는 사실' 카드는 역할 프롬프트에 들어간다."""
    from sillok_rag.corpus import load_chunks
    from sillok_rag.retrieval import BM25Retriever

    chunks = load_chunks()
    facts = [{"fact": "연명자는 최만리 등 7명이다.", "source": f"{PETITION}-14"}]
    s = ChatSession("D1", chunks, FakeLLM(), BM25Retriever(chunks), mode="role",
                    character="최만리", setting="1444년 2월 20일", cutoff="1444-02-20", known_facts=facts)
    t = s.ask("박팽년도 함께했지요?")
    system = t.messages[0]["content"]
    assert "[이 인물이 이 시점에 아는 사실]" in system
    assert "연명자는 최만리 등 7명이다." in system
    assert f"{PETITION}-14" not in t.context_ids


def test_role_rules_use_own_earlier_answers_but_not_user_claims():
    """v7: 인물은 앞선 대화의 자기 답을 아는 사실로 쓰고, 사관의 앞선 말은 확인 대상으로 본다(작업기록 [179]).
    사실 질문 규칙(v4)과 해설자 규칙에는 넣지 않는다."""
    from sillok_rag import config
    from sillok_rag.prompts import system_prompt

    role = system_prompt("role", chunks[:1], "세종", "1444년 2월 20일 저녁")
    assert "당신이 이미 말한 사실" in role and "상대(사관)가 앞서 한 말" in role
    assert "당신이 이미 말한 사실" not in system_prompt("fact", chunks[:1])
    assert "당신이 이미 말한 사실" not in system_prompt("narrator", chunks[:1])
    assert config.PROMPT_VERSION == "v9"
    # v9 기본값([232]): 전제가 다를 때만 "자료에 따르면 ~가 아니라 ~"로 바로잡고(평범한 질문은 대조 없이),
    # 인물은 사관 서술의 뒷날 호칭을 쓰지 않는다(역할 규칙 v8)
    fact = system_prompt("fact", chunks[:1])
    assert "아니라 병입니다" in fact and "대조 없이" in fact and '"아니다"로 시작해' not in fact
    assert "사관 서술에 나오는 호칭" in role


class _FixedOrder:
    """정해진 순서로만 청크를 돌려주는 가짜 검색기(임베딩 대신)."""
    def __init__(self, chunks, order):
        self.chunks, self.order = chunks, order

    def search(self, query, k, max_known=None):
        by_id = {c["chunk_id"]: c for c in self.chunks}
        picked = [by_id[i] for i in self.order
                  if max_known is None or (by_id[i]["known_key"] is not None and by_id[i]["known_key"] <= max_known)]
        return [(c, 1.0 - i / 1000) for i, c in enumerate(picked[:k])]   # 동점 없이 순서대로 낮아지는 점수


def test_hybrid_merges_ranks_and_keeps_time_filter():
    # 기사 하나(15청크)로 본다. 청크가 적어야 '순서를 뒤집으면 합친 점수가 거의 같다'가 성립한다.
    chunks = [c for c in load_chunks() if c["article_id"] == PETITION]
    bm25 = BM25Retriever(chunks)
    bm_order = [c["chunk_id"] for c, _ in bm25.search("정창손만 파직", len(chunks))]
    # 동점 없는 두 검색기의 순서를 정반대로 두면, 두 순위를 더한 점수는 모든 청크가 같아진다(점수 대신 순위만 씀).
    # BM25는 동점이 공동 순위를 받으므로 여기서는 가짜 검색기 두 개로 본다.
    hy = HybridRetriever(_FixedOrder(chunks, bm_order[::-1]), _FixedOrder(chunks, bm_order))
    hy.n = len(chunks)
    scores = [s for _, s in hy.search("정창손만 파직", len(chunks))]
    assert max(scores) - min(scores) < 1e-3
    # 두 검색기가 모두 1위로 꼽은 청크는 합친 결과에서도 1위다
    hy = HybridRetriever(_FixedOrder(chunks, bm_order), bm25)
    assert hy.search("정창손만 파직", 4)[0][0]["chunk_id"] == bm_order[0]
    # 시점 필터는 두 검색기 모두에 그대로 적용된다
    cut = known_key("1444-02-20")
    assert all(c["known_key"] <= cut for c, _ in hy.search("정창손만 파직", 4, max_known=cut))


def test_hybrid_ties_share_rank_so_file_order_does_not_matter():
    """BM25 0점 청크 수백 개가 코퍼스 줄 순서대로 다른 순위를 받아 후보가 바뀌던 문제(작업기록 [139]).
    동점은 공동(평균) 순위라, 코퍼스 순서를 뒤집어도 합친 점수가 같다."""
    from sillok_rag.retrieval import tie_ranks

    assert tie_ranks([(None, 5.0), (None, 3.0), (None, 3.0), (None, 0.0), (None, 0.0), (None, 0.0)]) == [1, 2.5, 2.5, 5, 5, 5]
    sub = chunks[:120]
    dense_order = [c["chunk_id"] for c in sub][::7] + [c["chunk_id"] for c in sub if c["chunk_id"] not in [x["chunk_id"] for x in sub][::7]]
    q = "최만리 상소"
    a = HybridRetriever(_FixedOrder(sub, dense_order), BM25Retriever(sub))
    b = HybridRetriever(_FixedOrder(sub, dense_order), BM25Retriever(sub[::-1]))
    sa = {c["chunk_id"]: s for c, s in a.search(q, len(sub))}
    sb = {c["chunk_id"]: s for c, s in b.search(q, len(sub))}
    assert sa.keys() == sb.keys() and all(abs(sa[k] - sb[k]) < 1e-12 for k in sa)


def test_hybrid_candidates_keep_each_retrievers_top():
    """한쪽 검색기만 위로 찾은 청크가 합친 순위에서 밀려도 리랭커 후보에는 꼭 들어간다(작업기록 [143])."""
    q = "정창손만 파직"
    bm25 = BM25Retriever(chunks)
    bm_top = [c["chunk_id"] for c, s in bm25.search(q, 3) if s > 0]
    dense_order = [c["chunk_id"] for c in chunks][::-1]          # BM25와 상관없는 임베딩 순서
    hy = HybridRetriever(_FixedOrder(chunks, dense_order), bm25, keep_each=3)
    hy.n = len(chunks)
    top2 = [c["chunk_id"] for c, _ in hy.search(q, 2)]
    cand = [c["chunk_id"] for c, _ in hy.candidates(q, 2)]
    assert len(cand) > 2 and set(top2) <= set(cand)
    assert set(bm_top) <= set(cand) and set(dense_order[:3]) <= set(cand)
    scores = [s for _, s in hy.candidates(q, 2)]
    assert scores == sorted(scores, reverse=True)                  # 합친 점수 순서
    assert hy.name == "hybrid-avgtie-keep3-date"                   # BM25 색인에 날짜([183]). 기본 BM25에는 풀이를 섞지 않음(C안, [302])
    mixed = HybridRetriever(_FixedOrder(chunks, dense_order), BM25Retriever(chunks, with_gloss=True, gloss_weight=0.5), keep_each=3)
    assert mixed.name == "hybrid-avgtie-keep3-date-gloss0.5"       # B안(풀이 섞기)은 이름으로 구별
    # 리랭커 없이 쓸 때(search)는 늘 k개
    assert len(hy.search(q, 4)) == 4


class PickLLM:
    """리랭커 시험용: 정해 둔 답(JSON 문자열)을 돌려준다."""
    dry_run = False

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat(self, messages, json_mode=False):
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _rerank(reply, query="김문은 어떤 벌을 받았나", k=4, max_known=None):
    from sillok_rag.retrieval import RerankRetriever

    base = BM25Retriever(chunks)
    cands = [c["chunk_id"] for c, _ in base.search(query, 20, max_known)]
    llm = PickLLM(reply(cands) if callable(reply) else reply)
    hits = RerankRetriever(base, llm, 20).search(query, k, max_known)
    return [c["chunk_id"] for c, _ in hits], cands, llm


def test_rerank_uses_model_order():
    import json

    ids, cands, llm = _rerank(lambda c: json.dumps({"ids": [c[9], c[3], c[15], c[0]]}))
    assert ids == [cands[9], cands[3], cands[15], cands[0]]
    assert len(llm.calls) == 1 and "[후보]" in llm.calls[0][1]["content"]


def test_rerank_fills_and_ignores_unknown_ids():
    import json

    # 후보에 없는 ID·중복은 버리고, 모자란 자리는 검색 순위대로 채운다
    ids, cands, _ = _rerank(lambda c: json.dumps({"ids": ["없는ID", c[5], c[5]]}))
    assert ids == [cands[5], cands[0], cands[1], cands[2]]


def test_rerank_falls_back_on_bad_output():
    ids, cands, _ = _rerank("JSON 아님")
    assert ids == cands[:4]
    ids, cands, _ = _rerank(RuntimeError("API 실패"))
    assert ids == cands[:4]


def test_rerank_skips_non_string_ids():
    """모델이 {"ids": [{}]}처럼 문자열이 아닌 것을 주면 멈추지 않고 건너뛴다(예전에는 TypeError, 중간 점검 보고서)."""
    import json

    ids, cands, _ = _rerank(json.dumps({"ids": [{}]}))
    assert ids == cands[:4]
    ids, cands, _ = _rerank(lambda c: json.dumps({"ids": [{}, ["x"], 3, c[5]]}))
    assert ids == [cands[5]] + [c for c in cands if c != cands[5]][:3]


def test_rerank_keeps_time_filter():
    import json

    cut = known_key("1444-02-20")
    ids, cands, _ = _rerank(lambda c: json.dumps({"ids": list(reversed(c))}), query="석방 파직 반포", max_known=cut)
    assert ids and all(key[i] is not None and key[i] <= cut for i in ids)


def test_rerank_check_keeps_only_verified_false_premises():
    import json

    from sillok_rag.retrieval import RerankRetriever

    base = BM25Retriever(chunks)
    q = "김문은 어떤 벌을 받았나"
    cands = [c for c, _ in base.search(q, 20)]
    top = cands[0]
    quote = top["translation"][:20]

    def reply(premise):
        return json.dumps({"ids": [c["chunk_id"] for c in cands[:4]], "premise": premise})

    ok = {"claim": "전제", "verdict": "틀림", "chunk": top["chunk_id"], "quote": quote, "correct": "바른 내용"}
    rr = RerankRetriever(base, PickLLM(reply([
        ok,
        {**ok, "verdict": "맞음"},                              # '맞음'은 넘기지 않는다
        {**ok, "quote": "자료에 없는 지어낸 근거 문장입니다"},       # 근거가 청크에 없으면 버린다
        {**ok, "chunk": cands[10]["chunk_id"]},                 # 고르지 않은 청크를 근거로 들면 버린다
        {**ok, "chunk": []},                                    # chunk가 문자열이 아니면 멈추지 않고 버린다
        {**ok, "chunk": {"id": top["chunk_id"]}},
        "틀림",                                                  # 판정이 객체가 아니면 버린다
    ])), 20, check=True)
    rr.search(q, 4)
    assert rr.name.endswith("_check")
    assert rr.last_premise == [{"claim": "전제", "chunk": top["chunk_id"], "quote": quote, "correct": "바른 내용"}]
    # 다음 검색에서 판정이 없으면 이전 판정이 남지 않는다
    rr.llm = PickLLM(reply([]))
    rr.search(q, 4)
    assert rr.last_premise == []


def test_premise_note_reaches_answer():
    class StubRetriever:
        name = "stub"
        last_premise = [{"claim": "갑이 했다", "chunk": KIM_MUN_PUNISHED, "quote": "근거", "correct": "을이 했다"}]

        def search(self, query, k, max_known=None):
            return [(c, 1.0) for c in chunks if c["chunk_id"] == KIM_MUN_PUNISHED]

    llm = FakeLLM()
    t = ChatSession("D2", chunks, llm, StubRetriever()).ask("갑이 한 일은?")
    assert "[답하기 전 점검" in t.messages[-1]["content"] and "을이 했다" in t.messages[-1]["content"]
    assert t.check and "갑이 했다" in t.check
    # 해설자에게는 넘기지 않는다
    s = ChatSession("D2", chunks, llm, StubRetriever(), mode="role", character="최만리", cutoff="1444-02-20")
    t = s.ask("역할을 잠깐 벗고 실제 역사를 알려 줘")
    assert t.speaker == "narrator" and "[답하기 전 점검" not in t.messages[-1]["content"]


def test_llm_params_follow_model_family():
    """새 모델(gpt-6)은 temperature를 빼고 생각 수준을 보내고, 옛 모델(gpt-4o-mini)은 temperature만 보낸다."""
    from sillok_rag.llm import LLM

    old = LLM(model="gpt-4o-mini-2024-07-18", dry_run=True, reasoning_effort="none")
    assert old.params() == {"temperature": 0} and old.reasoning_effort is None
    new = LLM(model="gpt-6-luna", dry_run=True, reasoning_effort="low")
    assert new.params(json_mode=True) == {"reasoning_effort": "low", "response_format": {"type": "json_object"}}
    assert LLM(model="gpt-6-luna", dry_run=True, reasoning_effort=None).params() == {}   # 생각 수준을 안 주면 모델 기본값
    assert LLM(dry_run=True).params() == {"reasoning_effort": "medium"}   # 기본값: gpt-6-luna, 생각 medium(10-07, [309])


def test_rerank_records_candidates_and_model_picks():
    """결과에 최종 4개만 남으면 정답이 후보 20개에서 빠졌는지, 리랭커가 버렸는지 알 수 없다(원인 분석 3-2)."""
    import json

    from sillok_rag.retrieval import RerankRetriever

    base = BM25Retriever(chunks)
    q = "김문은 어떤 벌을 받았나"
    cands = [c["chunk_id"] for c, _ in base.search(q, 20)]
    rr = RerankRetriever(base, PickLLM(json.dumps({"ids": ["없는ID", cands[7], cands[2]]})), 20)
    rr.search(q, 4)
    assert rr.last_trace == {"candidates": cands, "model_ids": [cands[7], cands[2]], "fallback": False}
    rr.llm = PickLLM(RuntimeError("API 실패"))
    rr.search(q, 4)
    assert rr.last_trace["fallback"] is True and rr.last_trace["model_ids"] == []
    # 대화 결과에도 그대로 실린다
    rr.llm = PickLLM(json.dumps({"ids": cands[:4]}))
    t = ChatSession("C", chunks, FakeLLM(), rr).ask(q)
    assert t.rerank_trace["candidates"] == cands and t.rerank_trace["model_ids"] == cands[:4]


def test_gloss_retriever_top_is_added_to_candidates_only():
    """C안: 풀이 BM25 상위는 리랭커 후보에만 보태고, 합친 순위(search)는 바꾸지 않는다(작업기록 [302])."""
    from sillok_rag.retrieval import gloss_extra

    q = "불교 책 찍는 기관"
    dense_order = [c["chunk_id"] for c in chunks][::-1]
    plain = HybridRetriever(_FixedOrder(chunks, dense_order), BM25Retriever(chunks), keep_each=3)
    plus = HybridRetriever(_FixedOrder(chunks, dense_order), BM25Retriever(chunks), keep_each=3, extra=gloss_extra(chunks))
    gloss_top = [c["chunk_id"] for c, s in gloss_extra(chunks)[0][0].search(q, config.GLOSS_KEEP) if s > 0]
    assert gloss_top and set(gloss_top) <= {c["chunk_id"] for c, _ in plus.candidates(q, 2)}
    assert [c["chunk_id"] for c, _ in plain.search(q, 4)] == [c["chunk_id"] for c, _ in plus.search(q, 4)]
    assert plus.name.endswith("-glosskeep%d" % config.GLOSS_KEEP)
    # 시점 필터는 풀이 BM25에도 같게
    cutoff = known_key("1444-02-20")
    assert all(allowed(c["chunk_id"], "1444-02-20") for c, _ in plus.candidates(q, 2, cutoff))
