"""시연 화면의 무료 회귀 검사. 가짜 검색 비교는 실제 임베딩 캐시 검증과 구분한다."""
import hashlib
import json
import re
import socket
from copy import deepcopy
from pathlib import Path

import pytest
from openai.resources.chat.completions import Completions
from openai.resources.embeddings import Embeddings
from streamlit.testing.v1 import AppTest

from ui import episode as ep
from ui import episode_gyeyu as GY
from ui import episodes
from ui import runtime, view
from sillok_rag import config, evaluate, retrieval, store
from sillok_rag.chat import ChatSession, TurnResult
from sillok_rag.cli import make_retriever
from sillok_rag.corpus import load_chunks, read_jsonl
from sillok_rag.llm import LLM


APP = Path(__file__).resolve().parents[1] / "app.py"
CHUNKS = load_chunks()
BY_ID = {c["chunk_id"]: c for c in CHUNKS}
SCENARIOS = evaluate.load_all_scenarios()


@pytest.fixture(autouse=True)
def forbid_paid_calls(monkeypatch):
    """실제 모델 생성과 소켓 접속을 막아 가짜 모델 밖의 유료 호출도 차단한다."""
    original_init = LLM.__init__
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def guarded_init(self, *args, **kwargs):
        assert kwargs.get("dry_run") is True, "무료 검사에서 실제 모델을 만들 수 없습니다."
        original_init(self, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("무료 검사에서 네트워크 접속이나 실제 임베딩을 시도했습니다.")

    def local_only(original):
        def connect(sock, address):
            # Windows asyncio가 내부 socketpair를 만들 때 쓰는 루프백만 허용한다.
            if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
                return original(sock, address)
            forbidden()
        return connect

    monkeypatch.setattr(LLM, "__init__", guarded_init)
    monkeypatch.setattr(LLM, "embed", forbidden)
    monkeypatch.setattr(Completions, "create", forbidden)
    monkeypatch.setattr(Embeddings, "create", forbidden)
    monkeypatch.setattr(socket.socket, "connect", local_only(original_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", local_only(original_connect_ex))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _app():
    return AppTest.from_file(str(APP), default_timeout=30).run()


def _click(app, key):
    app.button(key=key).click().run()
    assert not app.exception, app.exception


def _act(app, **action):
    """취재 화면 컴포넌트가 보내는 것과 같은 행동을 넣고 다시 실행한다(on_stage_action이 ss.pending에 넣는 것과 같은 길)."""
    app.session_state["pending"] = action
    app.run()
    assert not app.exception, app.exception


def _q(who, n):
    qid, text = ep.QUESTIONS[who][n]
    return {"type": "ask", "qid": qid, "text": text}


def _pick(app, card):
    """모드·사건 고르기 카드 컴포넌트가 보내는 것과 같은 고르기(on_pick이 ss.pick_pending에 넣는 것과 같은 길)."""
    app.session_state["pick_pending"] = card
    app.run()
    assert not app.exception, app.exception


def _tutorial():
    app = _app()
    _click(app, "go_start")
    _pick(app, "interview")
    _pick(app, "hunmin")
    assert app.session_state["page"] == "briefing"   # 먼저 취재 의뢰를 본다
    _click(app, "start_interview")
    return app


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_key_blocks_live_before_model_or_db(monkeypatch, key):
    if key is not None:
        monkeypatch.setenv("OPENAI_API_KEY", key)

    def unexpected(*args, **kwargs):
        pytest.fail("키 없는 실행이 DB나 모델 생성 단계로 넘어갔습니다.")

    monkeypatch.setattr(runtime, "chroma_ready", unexpected)
    monkeypatch.setattr(runtime, "LLM", unexpected)
    for make in (lambda: runtime.create_session(CHUNKS, preview=False),
                 lambda: runtime.open_interview(CHUNKS, "최만리", preview=False)):
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            make()
    monkeypatch.undo()   # 화면 검사는 키 없음 상태에서 미리보기로
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = _tutorial()
    _act(app, type="live", on=True)   # 키가 없으면 켜려 해도 미리보기에 머문다
    assert not app.session_state["live_on"]
    assert all(key.startswith("preview:") for key in app.session_state["talks"])


@pytest.mark.parametrize("ready,matches", [(False, False), (True, False)])
def test_missing_or_mismatched_db_blocks_live(monkeypatch, ready, matches):
    monkeypatch.setenv("OPENAI_API_KEY", "무료검사용가짜키")
    monkeypatch.setattr(runtime, "chroma_ready", lambda: ready)
    monkeypatch.setattr(runtime, "chroma_matches", lambda _: matches)
    for who in (None, "세종"):
        with pytest.raises(RuntimeError, match="검색 DB"):
            if who:
                runtime.open_interview(CHUNKS, who, preview=False)
            else:
                runtime.create_session(CHUNKS, preview=False)


def test_people_use_only_allowed_records_and_start_with_greeting():
    choe = runtime.open_interview(CHUNKS, "최만리")
    sejong = runtime.open_interview(CHUNKS, "세종")
    narrator = runtime.open_interview(CHUNKS, ep.NARRATOR)
    assert {c["chunk_id"] for c in choe.chunks} == set(ep.CHOE_IDS)
    # 세종이 정창손에게 한 앞선 말(-13)과 하옥 기록(-14)은 부름 전 최만리 자료에 없다
    assert f"{ep.P}13" not in ep.CHOE_IDS and f"{ep.P}14" not in ep.CHOE_IDS
    assert {f"{ep.P}13", f"{ep.P}14"} <= {c["chunk_id"] for c in sejong.chunks}
    assert len(narrator.chunks) == len(ep.NARRATOR_IDS) == 24 and narrator.mode == "fact"
    for name, session in (("최만리", choe), ("세종", sejong)):
        person = ep.PEOPLE[name]
        assert session.mode == "role" and session.cutoff == person["cutoff"]
        assert [(t.user, t.answer) for t in session.log] == [(person["setup"], person["greeting"])]
        assert "사관" not in person["setup"]
        # 연명자 명단 카드(-14 근거)는 최만리에게 주지 않는다
        assert all(f["source"] != f"{ep.P}14" for f in session.known_facts)
    assert all(BY_ID[cid] for cid in ep.NARRATOR_IDS)


def test_tutorial_questions_are_new_and_have_no_traps():
    scenario_questions = {t["user"] for s in SCENARIOS.values() for t in s["turns"]}
    asked = [q for pool in ep.QUESTIONS.values() for _, q in pool]
    assert len(asked) == len(set(asked)) and not set(asked) & scenario_questions
    ids = [qid for pool in ep.QUESTIONS.values() for qid, _ in pool]
    assert len(ids) == len(set(ids))


def test_preview_switch_keeps_each_interview_separate():
    app = _tutorial()
    _act(app, **_q("최만리", 0))
    _act(app, type="pick", who="세종")
    _act(app, **_q("세종", 0))
    talks = app.session_state["talks"]
    choe, sejong = talks["preview:최만리"], talks["preview:세종"]
    assert [t.user for t in choe.log][1:] == [ep.QUESTIONS["최만리"][0][1]]
    assert [t.user for t in sejong.log][1:] == [ep.QUESTIONS["세종"][0][1]]
    # 세종 대화의 이력에 최만리 면담이 섞이지 않는다
    assert all(ep.QUESTIONS["최만리"][0][1] not in m["content"] for m in sejong.log[-1].messages)
    _act(app, type="pick", who="최만리")
    assert app.session_state["who"] == "최만리" and ep.QUESTIONS["최만리"][0][0] in app.session_state["asked"]
    assert len(choe.log) == 2 and len(app.session_state["timeline"]) == 2
    _act(app, type="narrator")
    assert app.session_state["who"] == ep.NARRATOR
    _act(app, type="narrator")   # 다시 누르면 마지막 인물에게 돌아간다
    assert app.session_state["who"] == "최만리"


def test_scene_flow_to_notebook_and_back():
    app = _tutorial()
    _act(app, type="next")
    assert app.session_state["scene"] == 2
    qid, text = ep.QUESTIONS[(ep.NARRATOR, 2)][0]
    _act(app, type="ask", qid=qid, text=text)
    narrator = app.session_state["talks"][f"preview:{ep.NARRATOR}"]
    assert narrator.log[-1].user == text
    _act(app, type="back")
    assert app.session_state["scene"] == 1 and app.session_state["who"] == "최만리"
    _act(app, type="next")
    _act(app, type="next")
    assert app.session_state["scene"] == 3
    _act(app, type="next")
    assert app.session_state["page"] == "finale"
    _click(app, "finale_more")
    assert app.session_state["page"] == "episode" and app.session_state["scene"] == 1
    _act(app, type="events")   # 취재 화면 위쪽 메뉴 '← 사건 목록'
    assert app.session_state["page"] == "events"


def test_start_goes_through_modes_and_events():
    """시작하기 → 모드 고르기(취재하기·실록에 묻기·기출처럼 풀기) → 사건 고르기 → 취재 의뢰. 사건을 바꾸면 새로 시작한다."""
    app = _app()
    assert [b.key for b in app.button] == ["go_start"]   # 첫 화면은 시작하기 하나
    _click(app, "go_start")
    assert app.session_state["page"] == "modes"
    assert [b.key for b in app.button if b.key.startswith(("menu_", "open_"))] == ["menu_home"] and not app.toggle
    _pick(app, "interview")
    assert app.session_state["page"] == "events"
    assert [b.key for b in app.button if b.key.startswith("menu_")] == ["menu_modes", "menu_home"]
    _pick(app, "gyeyu")   # 계유정난도 열림(10-12)
    assert app.session_state["page"] == "briefing" and app.session_state["episode"] == "gyeyu"
    assert app.session_state["who"] == "수양대군"
    _click(app, "start_interview")
    _act(app, **{"type": "ask", "qid": "S01", "text": GY.QUESTIONS["수양대군"][0][1]})
    assert "S01" in app.session_state["asked"]
    _act(app, type="events")
    _pick(app, "gyeyu")   # 같은 사건을 다시 고르면 이어서
    assert "S01" in app.session_state["asked"]
    _click(app, "menu_events")
    _pick(app, "hunmin")   # 다른 사건으로 바꾸면 대화·수첩을 새로 시작
    assert app.session_state["page"] == "briefing" and app.session_state["episode"] == "hunmin"
    assert app.session_state["who"] == "최만리" and not app.session_state["asked"] and not app.session_state["talks"]
    _click(app, "start_interview")
    assert app.session_state["page"] == "episode"
    # 취재 화면은 컴포넌트 하나가 그리며 Streamlit 버튼(처음으로 등)을 따로 두지 않는다
    assert not [b for b in app.button if b.key and b.key.startswith(("menu_", "open_"))]


@pytest.mark.parametrize("module", list(episodes.EPISODES.values()), ids=list(episodes.EPISODES))
def test_episode_data_points_to_real_records(module):
    """사건 데이터의 청크·질문·목표가 서로 맞고 코퍼스에 있는지(계유정난을 더하며 두 사건에 같이 검사)."""
    for person in module.PEOPLE.values():
        assert set(person["allowed"]) <= set(module.NARRATOR_IDS) <= set(BY_ID)
        # 인물이 쓸 자료는 면담 시점(cutoff 날짜) 안의 기록만
        assert all(BY_ID[c]["known_from"][:10] <= person["cutoff"][:10] for c in person["allowed"])
        assert {"moment", "setup", "greeting", "goal", "switch_note", "hint"} <= set(person)
    ids = {qid for pool in module.QUESTIONS.values() for qid, _ in pool}
    assert set(module.QUESTION_PARTS) <= ids and {q for qs in module.FOLLOW_UPS.values() for q in qs} <= ids
    parts = {part for goal in module.GOALS.values() for part in goal["parts"]}
    assert set(module.QUESTION_PARTS.values()) <= parts == set(module.PART_LABELS) == set(module.PART_SUMMARIES)
    for goal in module.GOALS.values():
        for sources in goal["parts"].values():
            for cid, words in sources.items():   # 핵심 말(하나라도 있으면 됨)은 그 청크의 우리 번역에 있는 말이어야 잡힌다
                assert cid in BY_ID and (not words or any(w in BY_ID[cid]["translation"] for w in words)), (cid, words)
    assert all(c in BY_ID for scene in module.SCENES.values() for c in scene.get("card_sources", []))
    assert set(module.PORTRAITS) == set(module.PEOPLE) and len(module.BACKGROUNDS) in (2, 3)
    assert module.CARD["img"] and module.TITLE and module.STAY_NOTE and module.NARRATOR_HINT
    # 수첩은 대화 상대가 맡은 목표를 펼친다: 모든 목표에 맡은 사람이 있고, 인물마다 맡은 목표가 있다
    owners = [set(goal["people"]) for goal in module.GOALS.values()]
    assert all(owners) and set(module.PEOPLE) <= set().union(*owners) <= set(module.PEOPLE) | {module.NARRATOR}


def test_gyeyu_people_see_only_their_moment():
    """수양대군은 그날 밤 대궐까지, 권람은 대군이 김종서 집에 간 사이까지만 안다. 질문은 시나리오 D·E와 겹치지 않는다."""
    P = GY.P
    suyang, gwonram = set(GY.PEOPLE["수양대군"]["allowed"]), set(GY.PEOPLE["권람"]["allowed"])
    assert not {f"{P}39", f"{P}40", f"{P}41", f"{P}42"} & suyang   # 김종서가 다시 깨어난 일·이튿날 일은 모른다
    assert not {f"{P}{n}" for n in range(15, 21)} & gwonram and f"{P}25" not in gwonram   # 김종서 집 안의 일·결과는 모른다
    assert all(c.startswith(P) for c in suyang | gwonram)   # 1456·1457년 기록은 해설자만
    scenario_questions = {t["user"] for s in SCENARIOS.values() for t in s["turns"]}
    asked = [q for pool in GY.QUESTIONS.values() for _, q in pool]
    assert len(asked) == len(set(asked)) and not set(asked) & scenario_questions
    assert not {q for q, _ in sum(GY.QUESTIONS.values(), [])} & {q for q, _ in sum(ep.QUESTIONS.values(), [])}
    session = runtime.open_interview(CHUNKS, "권람", ep=GY)
    assert {c["chunk_id"] for c in session.chunks} == gwonram and session.log[0].answer == GY.PEOPLE["권람"]["greeting"]
    hit = runtime.goal_parts({"segments": [_seg(f"{P}09", "마땅히 먼저 (임금께) 아뢰어야 합니다")]}, GY.GOALS)
    assert set(hit) == {"2b"} and runtime.goal_parts({"segments": [_seg(f"{P}09", "마땅히 먼저")]}, GY.GOALS) == {}


def test_archive_menu_is_separate_and_removable():
    app = _app()
    _click(app, "go_start")
    _pick(app, "ask")
    _click(app, "archive_q1")
    records = app.session_state["archive"]
    assert len(records) == 1 and len(records[0].log) == 1 and len(records[0].log[0].messages) == 2
    assert "talks" not in app.session_state or not app.session_state["talks"]
    # 한 번에 답 하나만: 다른 질문을 보내면 앞의 답을 바꾼다(이어 붙이지 않음)
    _click(app, "archive_q2")
    records = app.session_state["archive"]
    assert len(records) == 1 and records[0].log[0].user == runtime.FACT_QUESTIONS[1]


def test_evidence_source_names_the_sillok_and_day():
    from ui import view
    assert view.sillok_source({"king": "세종", "reign": "세종 14년", "record_date": "1432-06-09"}) == "세종실록 · 세종 14년 6월 9일"
    assert view.sillok_source({"king": "연산군", "reign": "연산군 10년", "record_date": "1504-03-11"}) == "연산군일기 · 연산군 10년 3월 11일"
    assert view.sillok_source({"king": "선조(수정실록)", "reign": "선조(수정실록) 25년", "record_date": "1592-04-14"}) == "선조수정실록 · 선조 25년 4월 14일"
    assert view.sillok_source({"king": "태조", "reign": "즉위 전(총서)", "record_date": None}) == "태조실록 · 즉위 전(총서)"
    assert view.sillok_source({"king": "숙종", "reign": "숙종 3년", "record_date": "1677-04-05", "leap_month": True}) == "숙종실록 · 숙종 3년 윤4월 5일"


def _seg(source, quote, label="기록", verified=True):
    return {"text": "답 문장", "label": label, "source": source, "quote": quote, "verified": verified}


def test_goal_check_needs_record_sentence_from_goal_passage():
    hit = runtime.goal_parts({"segments": [_seg(f"{ep.P}06", "매질을 이기지 못해 억지로 자백하는")]})
    assert set(hit) == {"1c"}
    # -06 앞부분(상소가 가정한 옹호 논리)만 옮긴 구절은 반대 이유로 세지 않는다
    assert runtime.goal_parts({"segments": [_seg(f"{ep.P}06", "한 글자 차이로 억울함을 당할 수도")]}) == {}
    assert set(runtime.goal_parts({"segments": [_seg(f"{ep.P}09", "백성을 편하게 하려는 것이")]})) == {"2a"}
    assert runtime.goal_parts({"segments": [_seg(f"{ep.P}09", "너희가 운서를 아느냐")]}) == {}
    assert runtime.goal_parts({"segments": [_seg(f"{ep.P}04", "학문을 일으키는", label="해석")]}) == {}
    assert runtime.goal_parts({"segments": [_seg(f"{ep.P}04", "학문을 일으키는", verified=False)]}) == {}
    parts = runtime.goal_parts({"segments": [_seg(f"{ep.P}14", "의금부에 내렸다"), _seg(f"{ep.P}15", "석방하게 하되")]})
    assert set(parts) == {"3a", "3b"} and not runtime.goals_done(parts)["3"]
    parts["3c"] = ("wda_12809029_004-01", "")
    assert runtime.goals_done(parts)["3"]


def test_answer_hides_article_ids_but_keeps_text():
    """해설자 답 끝의 '근거: wda_…'는 화면에서 뺀다(근거 보기가 따로 있음, 사용자 10-12). 낱말 '근거'만 있는 문장은 그대로."""
    assert view.sentences_html("김문은 속전하게 했습니다.\n근거: wda_12602021_001-01") == ["김문은 속전하게 했습니다."]
    assert view.strip_source_ids("각각 110명이다(근거: wda_11406009_002-01, wda_11406009_002-02).") == "각각 110명이다."
    assert view.strip_source_ids("근거가 부족하다고 보았소.") == "근거가 부족하다고 보았소."
    assert "wda_" not in view.answer_html("확인되지 않는다. 출처: wda_12602020_001-15")
    # 10-12 리허설: 머리말이 '기사 ID'·'관련 기록'이면 ID만 빠지고 빈 괄호가 남았음
    assert view.strip_source_ids("각각 110명씩 골랐습니다. (기사 ID: wda_11406009_002-01)") == "각각 110명씩 골랐습니다."
    assert view.strip_source_ids("확인할 수 없습니다. (관련 기록: wga_10206002_002-01, wga_10206002_002-02)") == "확인할 수 없습니다."
    assert view.strip_source_ids("참고로 말하면 그렇소.") == "참고로 말하면 그렇소."


def test_sentences_html_splits_escapes_and_marks_first_terms():
    parts = view.sentences_html("<b>언문</b>을 썼소. 상소도 올렸소! 다시 언문 이야기\n끝")
    assert len(parts) == 4 and all("<b>" not in p for p in parts)
    assert sum(p.count('class="term"') for p in parts) == 2   # 같은 용어는 처음 한 번만
    assert 'data-term="언문"' in parts[0] and 'data-term="상소"' in parts[1]
    assert view.highlight_html("가<나>다 매질 끝", ["매질"]) == "가&lt;나&gt;다 <mark>매질</mark> 끝"


def test_answer_html_escapes_model_output_and_marks_terms():
    html = view.answer_html("<script>x</script> 언문과 상소, 다시 언문")
    assert "<script>" not in html and html.count('class="term"') == 2
    assert f'for="{view.TERM_IDS["언문"]}"' in html
    assert view.answer_tag({"segments": [_seg(f"{ep.P}04", "학문")]}) == "실록 기록 바탕"
    assert view.answer_tag({"segments": [_seg(f"{ep.P}04", "", label="해석")]}) == "실록 기반 풀이"
    assert view.answer_tag(None) == "기록 기반 재구성"


class ScriptedModel:
    """답변·근거 판정을 차례로 돌려주는 화면 검사용 모델. 첫 질문은 연결 실패를 흉내 낸다."""
    def __init__(self):
        self.calls = []
        self.answers = iter([ConnectionError("비밀 오류 문구"), "글을 알아도 매질 때문에 억울할 수 있소."])
        quote = "매질을 이기지 못해 억지로 자백하는 경우가 많으니"
        self.evidence = json.dumps({"segments": [{"text": "글을 알아도 매질 때문에 억울할 수 있소.", "label": "기록",
                                                  "source": f"{ep.P}06", "quote": quote}]}, ensure_ascii=False)

    def chat(self, messages, json_mode=False):
        self.calls.append((deepcopy(messages), json_mode))
        if json_mode:
            return self.evidence
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_notebook_materials_grouped_by_goal_with_highlight(monkeypatch):
    """수첩 '자료'는 근거 기사를 목표 갈래별로 묶고 답이 기댄 구절에 형광펜(<mark>)을 친다. 갈래에 없는 기사는 '그 밖의'로."""
    import types
    import app
    card = lambda cid, quote: {"chunk_id": cid, "title": BY_ID[cid]["title_ko"], "record_date": BY_ID[cid]["record_date"],
                               "translation": BY_ID[cid]["translation"], "quotes": [quote]}
    turn = TurnResult("질문", "답", "character", [], [])
    turn.evidence = {"cards": [card(f"{GY.P}08", "몰래 용(瑢, 안평대군)에게 붙어"), card(f"{GY.P}13", "하늘을 가리키며 맹세하기를")]}
    monkeypatch.setattr(app, "ss", types.SimpleNamespace(talks={"live:수양대군": types.SimpleNamespace(log=[turn])}))
    monkeypatch.setattr(app, "ep", GY)
    groups = app.material_groups()
    assert [g["label"] for g in groups] == ["① 거사의 명분 · 안평대군과 결탁 주장", "그 밖의 근거 기사"]
    assert "<mark>몰래 용(瑢, 안평대군)에게 붙어</mark>" in groups[0]["items"][0]["html"]


def test_suggestions_skip_questions_whose_goal_is_already_confirmed(monkeypatch):
    """겨냥한 목표 갈래가 이미 확인된 추천 질문은 다시 권하지 않는다(10-12 리허설)."""
    import types
    import app
    state = types.SimpleNamespace(talks={}, asked=set(), goals={})
    monkeypatch.setattr(app, "ss", state)
    monkeypatch.setattr(app, "ep", GY)
    ids = lambda: [q["qid"] for q in app.suggested(CHUNKS, "수양대군", 1, True)[0]]
    assert "S04" in ids()
    state.goals["1c"] = {"who": "수양대군", "source": f"{GY.P}28", "text": ""}
    assert "S04" not in ids() and "S02" in ids()


def test_typed_suggestion_counts_as_asked():
    """추천 질문과 같은 문장을 입력칸에 직접 쳐도 물은 것으로 세어 다시 권하지 않는다(10-12 리허설)."""
    app = _tutorial()
    qid, text = ep.QUESTIONS["최만리"][0]
    _act(app, type="ask", text=" " + text.rstrip("?") + " ")   # qid 없이, 띄어쓰기·물음표만 다름
    assert qid in app.session_state["asked"]


def test_live_switch_stays_on_across_pages(monkeypatch):
    """실록에 묻기의 스위치로 켠 뒤 스위치가 없는 취재 화면에서 여러 번 다시 그려도 꺼지지 않는다(10-12 리허설에서 답 한 번 뒤 꺼짐)."""
    preview_open = runtime.open_interview
    monkeypatch.setattr(runtime, "live_problem", lambda _: None)
    monkeypatch.setattr(runtime, "open_interview", lambda chunks, who, **kw: preview_open(chunks, who, ep=kw.get("ep", ep)))
    app = _app()
    _click(app, "go_start")
    _pick(app, "ask")
    app.toggle(key="live_toggle").set_value(True).run()
    assert app.session_state["live_on"]
    _click(app, "menu_modes")
    _pick(app, "interview")
    _pick(app, "hunmin")
    _click(app, "start_interview")
    for _ in range(3):
        _act(app, type="mark")
    assert app.session_state["live_on"]
    _act(app, type="live", on=False)   # 취재 화면 설정 창에서 끄기
    assert not app.session_state["live_on"]


def test_live_answer_checks_goal_and_retry_keeps_history(monkeypatch):
    model = ScriptedModel()

    def fake_open(chunks, who, **kwargs):
        person = ep.PEOPLE[who]
        subset = [c for c in chunks if c["chunk_id"] in set(person["allowed"])]
        session = ChatSession("D2", subset, model, retrieval.BM25Retriever(subset), mode="role", character=who,
                              setting=person["setup"], cutoff=person["cutoff"], known_facts=person["known_facts"])
        session.log.append(TurnResult(person["setup"], person["greeting"], "character", [], []))
        return session

    monkeypatch.setattr(runtime, "live_problem", lambda _: None)
    monkeypatch.setattr(runtime, "open_interview", fake_open)
    app = _tutorial()
    _act(app, type="live", on=True)
    assert app.session_state["live_on"] and not model.calls
    _act(app, **_q("최만리", 1))
    assert app.session_state["failure"]["text"] == ep.QUESTIONS["최만리"][1][1]
    assert "비밀 오류 문구" not in str(app.session_state["failure"])
    _act(app, type="retry")
    session = app.session_state["talks"]["live:최만리"]
    assert session.log[-1].answer.startswith("글을 알아도") and session.log[-1].evidence["error"] is None
    assert app.session_state["goals"]["1c"]["source"] == f"{ep.P}06" and app.session_state["failure"] is None
    calls = len(model.calls)
    app.run()
    assert len(model.calls) == calls   # 다시 그려도 근거 판정을 다시 부르지 않는다
    _act(app, type="mark")
    assert app.session_state["marks"][0]["a"].startswith("글을 알아도")
    _act(app, type="mark")   # 같은 답은 한 번만 표시
    assert len(app.session_state["marks"]) == 1


class FakeDense:
    """실제 DB·임베딩을 쓰지 않고 시점과 장면을 받는 고정 검색기."""
    name = "chroma"

    def __init__(self, chunks, embedder):
        self.chunks = chunks
        self.by_id = {c["chunk_id"]: c for c in chunks}

    def search(self, query, k, max_known=None, scene=None):
        allowed = [chunk for chunk in self.chunks if max_known is None or
                   (chunk["known_key"] is not None and chunk["known_key"] <= max_known)]
        allowed.sort(key=lambda chunk: hashlib.sha256(
            f"{scene or ''} {query} {chunk['chunk_id']}".encode()).digest())
        return [(chunk, 1 - index / len(self.chunks)) for index, chunk in enumerate(allowed[:k])]


class RecordedAnswer:
    model, embed_model, dry_run = config.ANSWER_MODEL, config.EMBED_MODEL, False
    reasoning_effort = config.ANSWER_EFFORT

    def __init__(self):
        self.calls = []

    def chat(self, messages, json_mode=False):
        self.calls.append(deepcopy(messages))
        return "무료 모의 응답"


class RecordedReranker(RecordedAnswer):
    model = config.RERANK_MODEL
    reasoning_effort = config.RERANK_EFFORT

    def chat(self, messages, json_mode=False):
        self.calls.append(deepcopy(messages))
        assert json_mode
        candidates = re.findall(r"^ID: (.+)$", messages[1]["content"], re.MULTILINE)
        ids = list(reversed(candidates[-config.TOP_K:]))
        chunk = next(chunk for chunk in CHUNKS if chunk["chunk_id"] == ids[0])
        return json.dumps({"ids": ids, "premise": [{
            "claim": "검사용 틀린 전제", "verdict": "틀림", "chunk": ids[0],
            "quote": chunk["translation"][:30], "correct": "검사용 바른 내용",
        }]}, ensure_ascii=False)


@pytest.fixture
def simulated_hybrid(monkeypatch):
    """실제 make_retriever의 하이브리드·BM25·리랭커를 쓰는 무료 모의 검증."""
    monkeypatch.setenv("OPENAI_API_KEY", "무료검사용가짜키")
    monkeypatch.setattr(retrieval, "ChromaRetriever", FakeDense)
    monkeypatch.setattr(runtime, "ChromaRetriever", FakeDense)
    monkeypatch.setattr(store, "chroma_ready", lambda: True)
    monkeypatch.setattr(store, "chroma_matches", lambda _: True)
    monkeypatch.setattr(runtime, "chroma_ready", lambda: True)
    monkeypatch.setattr(runtime, "chroma_matches", lambda _: True)


def test_live_interview_uses_measured_assembly_on_allowed_records(simulated_hybrid):
    """튜토리얼 면담도 측정한 검색 조립(하이브리드 + 풀이 후보 + 리랭커·전제 판정)이며 허용 자료만 쓴다."""
    answer, reranker = RecordedAnswer(), RecordedReranker()
    session = runtime.open_interview(CHUNKS, "최만리", preview=False, answer_llm=answer, rerank_llm=reranker)
    assert session.retriever.name == runtime.LIVE_RETRIEVER
    turn = runtime.ask_nonempty(session, ep.QUESTIONS["최만리"][0][1])
    assert set(turn.context_ids) <= set(ep.CHOE_IDS) and len(turn.context_ids) == config.TOP_K
    candidates = re.findall(r"^ID: (.+)$", reranker.calls[0][1]["content"], re.MULTILINE)
    assert candidates and set(candidates) <= set(ep.CHOE_IDS)
    messages = answer.calls[0]
    assert messages[1:3] == [{"role": "user", "content": ep.PEOPLE["최만리"]["setup"]},
                             {"role": "assistant", "content": ep.PEOPLE["최만리"]["greeting"]}]


def _same_turns(turns, rows):
    assert len(turns) == len(rows)
    for turn, row in zip(turns, rows):
        assert turn.user == row["question"]
        for name in ("answer", "speaker", "context_ids", "retrieved", "rerank_trace", "check", "search_scene"):
            assert getattr(turn, name) == row[name]
        assert len(turn.context_ids) == config.TOP_K
        assert turn.rerank_trace["fallback"] is False
        assert turn.rerank_trace["model_ids"] == turn.context_ids
        if turn.speaker != "narrator":
            assert turn.check and "검사용 틀린 전제" in turn.messages[-1]["content"]
        else:
            assert turn.check is None


def test_simulated_fact_contract_matches_run_single(simulated_hybrid, tmp_path):
    """실록 자료실 시연 세 문항의 후보 순서·근거·전제·두 모델 입력을 CLI 경로와 비교한다."""
    baseline_answer, baseline_reranker = RecordedAnswer(), RecordedReranker()
    baseline_retriever = make_retriever("hybrid", CHUNKS, baseline_answer, rerank_llm=baseline_reranker)
    questions = [item for item in evaluate.load_questions("holdout_v2_20261008")
                 if item["question"] in runtime.FACT_QUESTIONS]
    assert len(questions) == 3
    path = evaluate.run_single("D2", CHUNKS, baseline_answer, baseline_retriever,
                               set_name="holdout_v2_20261008", only=[item["id"] for item in questions],
                               out_path=tmp_path / "모의_단발.jsonl")
    turns, answer_calls, rerank_calls = [], [], []
    for item in questions:
        answer, reranker = RecordedAnswer(), RecordedReranker()
        session = runtime.create_session(CHUNKS, preview=False, answer_llm=answer, rerank_llm=reranker)
        assert session.retriever.name == runtime.LIVE_RETRIEVER
        turns.append(runtime.submit(session, item["question"]))
        answer_calls.extend(answer.calls)
        rerank_calls.extend(reranker.calls)
    _same_turns(turns, read_jsonl(path))
    assert answer_calls == baseline_answer.calls and rerank_calls == baseline_reranker.calls
    assert all(len(messages) == 2 for messages in answer_calls)


@pytest.mark.parametrize("sid", list(SCENARIOS))
def test_simulated_scene_contract_matches_run_scenario(simulated_hybrid, tmp_path, sid):
    """연결 함수가 기존 시나리오 실행 경로와 같은 입력을 만드는지 A-E 전체 턴으로 비교한다(화면에는 A-E를 쓰지 않음)."""
    baseline_answer, baseline_reranker = RecordedAnswer(), RecordedReranker()
    baseline_retriever = make_retriever("hybrid", CHUNKS, baseline_answer, rerank_llm=baseline_reranker)
    path = evaluate.run_scenario("D2", sid, CHUNKS, baseline_answer, baseline_retriever,
                                 out_path=tmp_path / f"모의_장면{sid}.jsonl")
    answer, reranker = RecordedAnswer(), RecordedReranker()
    scene = SCENARIOS[sid]
    session = runtime.create_session(CHUNKS, scene, preview=False, answer_llm=answer, rerank_llm=reranker)
    for item in scene["turns"]:
        runtime.submit(session, item["user"], scene)
    _same_turns(session.log, read_jsonl(path))
    assert answer.calls == baseline_answer.calls and reranker.calls == baseline_reranker.calls
    assert session.log[0].user == scene["setup"]
    assert session.known_facts == scene.get("known_facts", [])
    for index, turn in enumerate(session.log):
        if turn.speaker == "character":
            assert turn.search_scene
            for previous in session.log[:index]:
                if previous.speaker == "narrator":
                    assert {"role": "user", "content": previous.user} not in turn.messages[1:-1]


def test_asset_images_are_optional_and_shrunk(monkeypatch, tmp_path):
    from PIL import Image

    from ui import art
    monkeypatch.setattr(art, "ASSETS", tmp_path)
    assert art.asset_uri("portrait_choe", 520) is None   # 파일이 없으면 SVG를 쓴다
    Image.new("RGB", (1200, 1500), "navy").save(tmp_path / "portrait_choe.png")
    uri = art.asset_uri("portrait_choe", 520)
    assert uri.startswith("data:image/jpeg;base64,")
    import base64, io
    with Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))) as img:
        assert img.size == (520, 650)


def test_notebook_source_shows_article_title_and_date():
    """수첩 근거 표시는 청크 ID·문단 번호(wda_… 5문단) 대신 기사 제목(날짜)이다."""
    import app
    chunk = BY_ID[f"{ep.P}06"]
    label = app.source_label(chunk)
    assert label == f"{chunk['title_ko']}({chunk['record_date']})" and "wda_" not in label


def test_ui_parts_crop_faint_edges(monkeypatch, tmp_path):
    """이미지 AI 그림 가장자리의 거의 투명한 얼룩(알파 8 이하)은 잘라 낸다(stage.css 자르기 값의 기준)."""
    import base64, io
    from PIL import Image

    from ui import art
    monkeypatch.setattr(art, "ASSETS", tmp_path)
    img = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    img.paste((200, 150, 80, 255), (50, 40, 250, 160))   # 실제 테두리 그림
    img.putpixel((2, 2), (0, 0, 0, 5))                   # 가장자리 얼룩
    img.save(tmp_path / "panel_dark.png")
    uri = art.asset_png("panel_dark", 600)
    with Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))) as out:
        assert out.size == (200, 120)


def test_shrunk_images_are_cached_until_original_changes(monkeypatch, tmp_path):
    """줄인 그림은 assets/sized/에 남아 다시 켜도 쓰고, 원본을 바꾸면 다시 만든다."""
    import os
    from PIL import Image

    from ui import art
    monkeypatch.setattr(art, "ASSETS", tmp_path)
    Image.new("RGB", (1200, 600), "navy").save(tmp_path / "bg_home.png")
    first = art.asset_uri("bg_home", 600)
    cache = tmp_path / "sized" / "bg_home_jpg600"
    assert cache.exists()
    cache.write_bytes(b"cached")                          # 캐시가 있으면 원본을 다시 줄이지 않는다
    os.utime(cache, ns=((tmp_path / "bg_home.png").stat().st_mtime_ns,) * 2)
    assert art.asset_uri("bg_home", 600).endswith(",Y2FjaGVk")   # base64("cached")
    Image.new("RGB", (1200, 600), "red").save(tmp_path / "bg_home.png")
    os.utime(tmp_path / "bg_home.png", ns=(1, 1))         # 원본을 바꾸면(시각이 달라지면) 다시 만든다
    again = art.asset_uri("bg_home", 600)
    assert again != first and not again.endswith(",Y2FjaGVk")


def test_warm_assets_builds_all_caches_and_lists_missing(monkeypatch, tmp_path):
    """첫 접속 때 화면이 쓰는 그림을 모두 미리 줄이고, 없는 그림 이름을 돌려준다."""
    from PIL import Image

    import app
    from ui import art
    monkeypatch.setattr(art, "ASSETS", tmp_path)
    Image.new("RGB", (2000, 1000), "navy").save(tmp_path / "bg_home.png")
    missing = app.warm_assets()
    assert (tmp_path / "sized" / "bg_home_jpg1600").exists()
    assert "bg_home" not in missing and {"card_mode_quiz", "portrait_choe_cut", "panel_dark"} <= set(missing)


def test_home_does_not_wait_for_search_db(monkeypatch):
    """첫 화면은 검색 DB 확인을 기다리지 않는다(DB 준비는 뒤에서 하는 warm-up 스레드만 한다)."""
    import threading

    callers = []
    monkeypatch.setattr(runtime, "live_problem", lambda _: callers.append(threading.current_thread().name))
    app = _app()
    assert not app.exception, app.exception
    assert all(name == "warm-up" for name in callers), callers
    _click(app, "go_start")   # 모드 화면부터는 설정 메뉴가 있어 확인한다
    assert any(name != "warm-up" for name in callers), callers


def test_fast_trial_is_off_by_default_and_keeps_evidence_shape():
    """시험 모드는 기본으로 꺼져 있고(측정 설정), 켜면 쓰는 근거 대조도 evidence.annotate와 같은 형식이다."""
    import json

    from ui import fast_trial
    assert fast_trial.ON is False and runtime.SETTINGS_LABEL.startswith("측정 설정")
    chunk = BY_ID[f"{ep.P}14"]
    answer = "그렇지 않소. 신석조와 김문도 함께 이름을 올렸소."
    assert fast_trial.sentences(answer) == ["그렇지 않소.", "신석조와 김문도 함께 이름을 올렸소."]

    class Fake:
        def chat(self, messages, json_mode=False):
            assert "1. 그렇지 않소." in messages[1]["content"]
            return json.dumps({"labels": [
                {"n": 1, "label": "해석", "source": chunk["chunk_id"]},
                {"n": 2, "label": "기록", "source": chunk["chunk_id"], "quote": "직제학(直提學) 신석조(辛碩祖), 직전(直殿) 김문"},
                {"n": 9, "label": "기록", "source": chunk["chunk_id"], "quote": "없는 번호"}]})

    ev = fast_trial.annotate(Fake(), answer, [chunk])
    assert [s["label"] for s in ev["segments"]] == ["해석", "기록"] and ev["segments"][1]["verified"]
    assert ev["show_button"] and ev["cards"][0]["chunk_id"] == chunk["chunk_id"] and ev["error"] is None


def test_quiz_is_checked_five_choice_from_corpus_without_api(monkeypatch):
    """기출처럼 풀기: 5지선다, 정답·근거 청크가 코퍼스에 있고, 풀어도 API를 부르지 않는다."""
    for q in ep.QUIZ:
        assert len(q["options"]) == 5 and 1 <= q["answer"] <= 5 and q["sources"]
        assert all(cid in BY_ID for cid in q["sources"])
    monkeypatch.setattr(Completions, "create", lambda *a, **k: pytest.fail("API 호출"))
    app = _app()
    _click(app, "go_start")
    _pick(app, "quiz")
    assert app.session_state["page"] == "quiz"
    first = ep.QUIZ[0]
    _click(app, f"qz_{first['id']}_{first['answer']}")
    assert app.session_state["quiz"]["picked"][first["id"]] == first["answer"]
    _click(app, "qz_next")
    assert app.session_state["quiz"]["i"] == 1


def test_notebook_focus_follows_person():
    """대화 상대가 맡은 목표 중 아직 확인 안 된 첫 목표를 펼친다(다 확인됐으면 첫 목표, 맡은 목표가 없으면 없음)."""
    import app
    from ui import episode
    old = app.ep
    app.ep = episode
    try:
        none_done = {gid: False for gid in episode.GOALS}
        assert app.focus_goal("최만리", none_done) == "1"
        assert app.focus_goal("세종", none_done) == "2"
        assert app.focus_goal("세종", {**none_done, "2": True}) == "3"
        assert app.focus_goal("세종", {gid: True for gid in episode.GOALS}) == "2"
        assert app.focus_goal("없는 사람", none_done) is None
    finally:
        app.ep = old


def test_sized_images_work_without_originals(monkeypatch, tmp_path):
    """저장소만 받아 원본이 없어도 sized/의 줄인 그림을 그대로 쓴다. 둘 다 없으면 None(대체 그림)."""
    from ui import art
    monkeypatch.setattr(art, "ASSETS", tmp_path)
    (tmp_path / "sized").mkdir()
    (tmp_path / "sized" / "bg_home_jpg1600").write_bytes(b"cached")
    assert art.asset_uri("bg_home", 1600).endswith(",Y2FjaGVk")
    assert art.asset_uri("bg_none", 1600) is None


def test_source_notice_on_home_and_evidence():
    """공공누리 제1유형 출처 표시가 첫 화면과 근거 기사 창(두 화면 모두)에 있다."""
    from ui import view
    stage_js = (Path(__file__).resolve().parents[1] / "ui/stage_files/stage.js").read_text(encoding="utf-8")
    assert view.SOURCE_NOTICE in stage_js and "공공누리 제1유형" in view.CREDIT_NOTICE
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not app.exception and any(view.SOURCE_NOTICE in str(h.proto) for h in app.get("html"))
