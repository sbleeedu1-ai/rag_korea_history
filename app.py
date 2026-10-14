"""역사 취재록 화면(취재하기·실록에 묻기·기출처럼 풀기). 실행: python -m streamlit run app.py

설계: docs/서비스설계.md 엔진(sillok_rag/)은 그대로 쓰고,
사건 데이터는 ui/episodes.py(언문 논쟁 episode.py·계유정난 episode_gyeyu.py), 엔진 연결은 ui/runtime.py에 있다.
"""
import base64
import threading
from html import escape
from pathlib import Path

import streamlit as st

from ui import archive_page, episodes, picker, quiz_page, runtime, stage, view
from ui.art import ASSETS, asset_png, asset_uri, courtyard, portrait
from sillok_rag.corpus import load_chunks

ROOT = Path(__file__).resolve().parent
# 모드 고르기 화면의 '실록에 묻기'·'기출처럼 풀기'가 여는 화면(10-12 [389]). {페이지 이름: (제목, 설명, 화면 함수)}
EXTRA_PAGES = {"archive": (archive_page.NAME, archive_page.SUBTITLE, archive_page.render),
               "quiz": (quiz_page.NAME, quiz_page.SUBTITLE, quiz_page.render)}

st.set_page_config(page_title="역사 취재록", page_icon="📜", layout="wide")
st.html(f"<style>{(ROOT / 'ui/style.css').read_text(encoding='utf-8')}</style>")
ss = st.session_state
# 지금 사건의 데이터 모듈. main()이 실행마다 ss.episode로 다시 정한다(아래 함수들은 이 이름을 그대로 씀)
ep = episodes.EPISODES[episodes.DEFAULT]


@st.cache_data
def chunks_all():
    return load_chunks()


@st.cache_data
def backdrop(name="bg_scene1"):
    """배경 그림(assets/에 있으면 그 그림, 없으면 언문 논쟁 배경, 그것도 없으면 SVG 궁궐)."""
    return f"url({background(name)})"


@st.cache_data
def face(name, file):
    """초상 그림의 src(assets/에 있으면 그 그림, 없으면 SVG 창작 삽화)."""
    return (asset_uri(file, 520)
            or "data:image/svg+xml;base64," + base64.b64encode(portrait(name).encode()).decode())


def fresh_episode(module):
    """사건 하나의 취재 상태(처음 상태). 사건을 바꾸면 이 값들로 새로 시작한다."""
    first = next(iter(module.PEOPLE))
    return {"episode": module.ID, "scene": 1, "who": first, "last_person": first, "talks": {}, "timeline": [], "goals": {},
            "asked": set(), "marks": [], "shown": {}, "failure": None, "memo": ""}


def init_state():
    for key, value in {"page": "home", **fresh_episode(episodes.EPISODES[episodes.DEFAULT])}.items():
        ss.setdefault(key, value)


def enter_episode(eid):
    """사건 카드를 고르면 그 사건의 취재 의뢰로. 다른 사건으로 바꾸면 대화·수첩을 새로 시작한다(같은 사건이면 이어서)."""
    if ss.episode != eid:
        ss.update(fresh_episode(episodes.EPISODES[eid]))
    go("briefing")


def go(page, **extra):
    ss.page = page
    ss.update(extra)


def live_mode(chunks):
    """(미리보기 여부, 실제 실행을 막는 문제). 실제 답변은 설정에서 켜야 하고 키·DB가 맞아야 한다."""
    problem = runtime.live_problem(chunks)
    return not (ss.get("live_on") and problem is None), problem


def talk_key(who, preview):
    return f"{'preview' if preview else 'live'}:{who}"


def talk(chunks, who, preview):
    """인물·해설자마다 대화를 따로 보관한다. 다른 면담의 말은 섞이지 않는다."""
    key = talk_key(who, preview)
    if key not in ss.talks:
        ss.talks[key] = runtime.open_interview(chunks, who, preview=preview, ep=ep)
    return ss.talks[key]


def speaker_name(session, turn):
    return session.character if turn.speaker == "character" else ep.NARRATOR


# ---------- 공통 머리 ----------

def settings_menu(problem):
    with st.popover("설정 ⚙", use_container_width=True):
        # 켜짐 값은 위젯 키가 아닌 ss.live_on에 둔다. 위젯 키에 두면 이 스위치가 없는 취재 화면에서 Streamlit이 값을 지워
        # 답 한 번 뒤 실제 답변이 꺼졌다(10-12 사용자 리허설 "한 번 답변이후 API 가 계속 풀리네"). 스위치는 그려질 때마다 live_on을 따라감
        ss.live_toggle = bool(ss.get("live_on"))
        st.toggle("실제 답변 켜기 · API 비용 발생", key="live_toggle", disabled=problem is not None,
                  on_change=lambda: ss.update(live_on=ss.live_toggle))
        if problem:
            st.caption(problem)
            st.caption("지금은 비용 없는 미리보기로 화면만 확인할 수 있습니다.")
        st.caption("질문 하나에 답변·자료 고르기·근거 대조 호출이 함께 듭니다.")
        st.caption(runtime.SETTINGS_LABEL)


# 화면마다 필요한 위쪽 버튼만 보인다([361]): 설정(실제 답변 켜기)은 질문을 보내는 화면에만
TOP_MENUS = {"modes": ("home",), "events": ("modes", "home"), "briefing": ("events", "home"), "finale": ("events", "home"),
             "archive": ("settings", "modes", "home"),
             "quiz": ("modes", "home")}   # 기출처럼 풀기는 API를 부르지 않아 설정(실제 답변 켜기)이 필요 없다


def topbar(problem):
    items = TOP_MENUS.get(ss.page, ("home",))
    with st.container(key="topbar"):
        _topbar(items, problem)


def _topbar(items, problem):
    left, right = st.columns([3, 2.4])
    left.html('<div class="brand">역사 취재록</div>')
    with right:
        cols = st.columns([4 - len(items) or 0.01] + [1] * len(items))[1:]   # 오른쪽 끝에 붙인다
        for col, item in zip(cols, items):
            if item == "settings":
                with col:
                    settings_menu(problem)
            elif item == "modes":
                col.button("← 모드 선택", key="menu_modes", use_container_width=True, on_click=go, args=("modes",))
            elif item == "events":
                col.button("← 사건 목록", key="menu_events", use_container_width=True, on_click=go, args=("events",))
            else:
                col.button("처음으로", key="menu_home", use_container_width=True, on_click=go, args=("home",))


def brief_html():
    rows = "".join(f'<div class="brief-row"><span class="brief-no">{no}</span><div><b>{escape(q)}</b>'
                   f'<p>{escape(who)} · {escape(when)}</p></div></div>' for no, who, q, when in ep.BRIEF_ITEMS)
    return (f'<div class="brief"><div class="eyebrow">취재 의뢰 · {ep.EPISODE_LABEL}</div><h2>{ep.TITLE}</h2>'
            f'<p class="brief-text">{escape(ep.INTRO)}</p><div class="brief-list">{rows}</div>'
            f'<p class="brief-note">{escape(ep.BRIEF_NOTE)}</p></div>')


def briefing():
    """튜토리얼에 들어가면 먼저 보는 취재 의뢰 화면. 읽고 나서 두 인물 화면으로 간다."""
    with st.container(key="briefing"):
        st.html(brief_html())
        _, mid, _ = st.columns([1, 1, 1])
        mid.button("취재 시작  →", key="start_interview", type="primary", use_container_width=True,
                   on_click=go, args=("episode",), kwargs={"scene": 1})


# ---------- 페이지 ----------

def home():
    st.html(f'<div class="hero" style="background-image:linear-gradient(180deg,rgba(9,14,22,.35),rgba(9,14,22,.82)),{backdrop("bg_home")}">'
            '<div class="eyebrow">사건 속으로 들어가는 역사 인터뷰</div><div class="ornament">◆</div>'
            '<h1>역사 취재록</h1><div class="ornament">◆</div>'
            '<p>인물을 만나고, 기록을 확인하고, 나만의 취재를 완성하세요.</p></div>')
    with st.container(key="home_actions"):
        st.button("시작하기  ›", key="go_start", type="primary", use_container_width=True, on_click=go, args=("modes",))
    st.html('<div class="footer">─ 실록을 바탕으로 재구성한 역사 학습 체험 ─</div>'
            f'<div class="footer credit">{escape(view.CREDIT_NOTICE)}</div>')


# ---------- 모드·사건 고르기(카드 컴포넌트, 10-12 [389]) ----------

PICK_ROUTES = {"interview": "events", "ask": "archive", "quiz": "quiz"}   # 카드 id → 갈 화면(사건 카드는 enter_episode)


@st.cache_data
def card_art(name):
    return asset_uri(name, 560)


def on_pick(key):
    state = ss.get(key)
    try:
        picked = state["pick"]
    except (KeyError, TypeError):
        picked = getattr(state, "pick", None)
    if picked:
        ss.pick_pending = picked.get("id")


def handle_pick():
    """카드에서 고른 것을 화면 이동으로(테스트는 ss.pick_pending에 카드 id를 넣어 같은 길을 탄다)."""
    picked = ss.pop("pick_pending", None)
    if picked in PICK_ROUTES:
        go(PICK_ROUTES[picked])
    elif picked in episodes.EPISODES:
        enter_episode(picked)


def modes():
    st.html('<div class="page-head center"><span class="eyebrow">모드 선택</span><h1>무엇을 해 볼까요?</h1>'
            '<p>사건 속 인물을 취재하거나, 실록에 직접 묻거나, 기출처럼 풀어 보세요.</p></div>')
    cards = [
        {"id": "interview", "title": "취재하기", "sub": "사건 속 인물을 만나 직접 묻기", "img": card_art("card_mode_interview"), "fx": "lantern"},
        {"id": "ask", "title": "실록에 묻기", "sub": "실록 자료로 무엇이든 묻기 · 없는 건 지어내지 않음",
         "img": card_art("card_mode_ask_closed"), "img_hover": card_art("card_mode_ask"), "fx": "book"},
        {"id": "quiz", "title": "기출처럼 풀기", "sub": "취재한 사건을 한국사능력검정시험처럼 5지선다로", "img": card_art("card_mode_quiz"), "fx": "sun"},
    ]
    picker.mount({"cards": cards}, key="pick_modes", on_pick=lambda: on_pick("pick_modes"))


def events():
    st.html('<div class="page-head center"><span class="eyebrow">취재하기 · 사건 선택</span><h1>어떤 사건을 취재할까요?</h1>'
            '<p>사건마다 인물과 기록을 검수해 준비합니다.</p></div>')
    # 사건마다 데이터 모듈의 CARD 한 줄(10-12 계유정난을 열어 '준비 중' 카드는 없어짐)
    cards = [{**module.CARD, "id": eid, "img": card_art(module.CARD["img"])} for eid, module in episodes.EPISODES.items()]
    picker.mount({"cards": cards}, key="pick_events", on_pick=lambda: on_pick("pick_events"))


# ---------- 취재 화면(컴포넌트) ----------

STAGE_KEY = "stage"
UI_ASSETS = {   # 이름: 화면에 쓸 너비(px). 테두리 그림의 border-image 자르기 값은 stage.css가 이 너비 기준으로 정한다
    "notebook": 330, "panel_dark": 600, "panel_paper": 700, "nameplate": 480, "divider": 900, "frame_portrait": 420,
    "icon_book": 96, "icon_doc": 96, "icon_bookmark": 96, "icon_pencil": 96, "icon_books": 96, "icon_gear": 96,
    "scroll_roller": 48, "scroll_paper": 900,   # 취재 목표 두루마리(축은 좌우 반전해 양쪽에, 종이는 너비에 맞춰 늘림)
}


@st.cache_data
def ui_assets():
    found = {name: asset_png(name, width) for name, width in UI_ASSETS.items()}
    found["icon_narrator"] = asset_uri("icon_narrator", 96)
    return {name: uri for name, uri in found.items() if uri}


@st.cache_data
def cutout(name):
    """카드 안에 넣을 초상: 배경을 지운 그림이 있으면 그것, 없으면 일반 초상."""
    return asset_png(ep.PORTRAITS[name] + "_cut", 520) or face(name, ep.PORTRAITS[name])


@st.cache_data
def background(name):
    """배경 그림의 src. 사건 전용 그림이 아직 없으면 언문 논쟁 배경을 빌려 쓴다."""
    return (asset_uri(name, 1600) or asset_uri("bg_scene1", 1600)
            or "data:image/svg+xml;base64," + base64.b64encode(courtyard().encode()).decode())


def stage_state(name):
    state = ss.get(STAGE_KEY)
    if state is None:
        return None
    try:
        return state[name]
    except (KeyError, TypeError):
        return getattr(state, name, None)


def on_stage_action():
    action = stage_state("action")
    if action:
        ss.pending = dict(action)


def on_stage_memo():
    ss.memo = stage_state("memo") or ""


def current_who():
    return ss.who if ss.scene == 1 else ep.NARRATOR


def shown_index(session, who, scene):
    """대화창에 보일 턴. 인물은 마지막 턴(첫 턴은 미리 쓴 인사), 해설자는 이 장면에서 마지막으로 받은 턴(없으면 None)."""
    index = ss.shown.get((who, scene)) if who == ep.NARRATOR else len(session.log) - 1
    while index is not None and index > 0 and not (session.log[index].answer or "").strip():
        index -= 1   # 빈 답은 건너뛰고 마지막으로 받은 답을 보인다
    return index


def run_ask(chunks, who, scene, text, qid, preview):
    """질문을 보내고, 실제 실행이면 근거 판정으로 목표를 확인한다. 실패해도 대화는 보존한다.
    근거 대조를 답 뒤로 미뤘다가([400]) 되돌림([401]): 목표 확인이 답과 따로 놀고, 대조 중 다른 질문을 누르면 꼬임(사용자 10-12)."""
    key = talk_key(who, preview)
    session = talk(chunks, who, preview)
    try:
        if not preview and runtime.live_problem(chunks):
            raise RuntimeError("실제 실행 준비 필요")
        turn = runtime.ask_and_check(session, text, preview)
    except Exception:
        # API 키 등이 담길 수 있는 예외 전문은 화면에 쓰지 않는다
        ss.failure = {"key": key, "who": who, "text": text, "qid": qid}
        return
    index = len(session.log) - 1
    ss.failure = None
    ss.timeline.append({"scene": scene, "key": key, "index": index})
    if qid:
        ss.asked.add(qid)
    if who == ep.NARRATOR:
        ss.shown[(who, scene)] = index
    apply_goals(session, turn)


def apply_goals(session, turn):
    """근거 판정에서 확인된 목표 갈래를 수첩에 넣는다."""
    for part, (source, sentence) in runtime.goal_parts(turn.evidence, ep.GOALS).items():
        if part not in ss.goals:
            ss.goals[part] = {"who": speaker_name(session, turn), "source": source, "text": sentence}
            gid = next(g for g, goal in ep.GOALS.items() if part in goal["parts"])
            st.toast(f"수첩에 기록했습니다 · {ep.GOALS[gid]['title']}")


def qid_of(who, scene, text):
    """입력칸에 추천 질문과 같은 문장을 직접 쳐도 그 질문을 물은 것으로 센다(10-12 리허설: 친 질문이 다시 추천됨).
    띄어쓰기·끝 문장부호 차이는 무시한다."""
    norm = lambda t: "".join(t.split()).rstrip("?？.")
    pool = ep.QUESTIONS[who] if who in ep.PEOPLE else ep.QUESTIONS.get((ep.NARRATOR, scene), [])
    return next((qid for qid, q in pool if norm(q) == norm(text)), None)


def handle(chunks, preview, action):
    """화면에서 온 행동 하나를 처리한다(테스트는 ss.pending에 행동을 넣어 같은 길을 탄다)."""
    kind, scene = action.get("type"), ss.scene
    if kind == "pick" and action.get("who") in ep.PEOPLE:
        ss.who = ss.last_person = action["who"]
        st.toast(ep.PEOPLE[ss.who]["switch_note"])
    elif kind == "narrator" and scene == 1:
        ss.who = ss.last_person if ss.who == ep.NARRATOR else ep.NARRATOR
    elif kind == "ask" and (action.get("text") or "").strip():
        who, text = current_who(), action["text"].strip()
        run_ask(chunks, who, scene, text, action.get("qid") or qid_of(who, scene, text), preview)
    elif kind == "retry" and ss.failure:
        failure = ss.failure
        run_ask(chunks, failure["who"], scene, failure["text"], failure["qid"], preview)
    elif kind == "next":
        if scene < 3:
            ss.scene, ss.who = scene + 1, ep.NARRATOR
        else:
            go("finale")
    elif kind == "back":
        ss.scene, ss.who = 1, ss.last_person
    elif kind == "mark":
        who = current_who()
        session = talk(chunks, who, preview)
        index = shown_index(session, who, scene)
        key = talk_key(who, preview)
        if index and not any(m["id"] == (key, index) for m in ss.marks):
            turn = session.log[index]
            ss.marks.append({"id": (key, index), "who": speaker_name(session, turn), "q": turn.user, "a": turn.answer})
            st.toast("수첩에 표시했습니다.")
    elif kind == "live":
        ss.live_on = bool(action.get("on")) and runtime.live_problem(chunks) is None
    elif kind == "events":
        go("events")


def preview_text(session, turn, chunks):
    by_id = {c["chunk_id"]: c for c in chunks}
    titles = [f"{by_id[c]['title_ko']}({by_id[c]['record_date'] or '총서'})" for c in turn.context_ids if c in by_id]
    found = ", ".join(dict.fromkeys(titles))
    who = speaker_name(session, turn)
    return (f"(미리보기) 실제 답변을 켜면 이 자리에 {who}의 답이 나옵니다. "
            f"이번 질문으로 찾은 자료: {found or '없음'}")


def dialogue_data(chunks, who, preview, scene):
    session = talk(chunks, who, preview)
    index = shown_index(session, who, scene)
    key = talk_key(who, preview)
    if index is None:   # 해설자 첫 화면: 장면의 기록 카드
        text = ep.SCENES[scene].get("card") or "배경과 뒤의 기록이 궁금하면 물어보세요. 해설자는 기록에 적힌 범위에서 설명합니다."
        return {"id": f"{key}:card:{scene}", "speaker": ep.NARRATOR, "narrator": True, "tag": "기록 요약", "question": "",
                "sentences": view.sentences_html(text, ep.INLINE_TERMS), "canEvidence": False, "marked": False, "cards": []}
    turn = session.log[index]
    name = speaker_name(session, turn)
    first = index == 0 and who != ep.NARRATOR
    text = preview_text(session, turn, chunks) if preview and not first else turn.answer
    cards = [{"title": c["title"], "date": c.get("record_date") or "날짜 없는 총서", "speaker": c["speaker"],
              "translation_html": view.highlight_html(c["translation"], c.get("quotes", [])),
              "original": c["original"], "url": c["url"]} for c in (turn.evidence or {}).get("cards", [])]
    return {"id": f"{key}:{index}", "speaker": name, "narrator": name == ep.NARRATOR,
            "tag": "기록 기반 재구성" if first else view.answer_tag(turn.evidence),
            "question": "" if first else turn.user, "sentences": view.sentences_html(text, ep.INLINE_TERMS),
            "canEvidence": not first and not preview, "marked": any(m["id"] == (key, index) for m in ss.marks), "cards": cards}


def source_label(chunk):
    """수첩에 보일 근거 표시: 기사 제목(날짜). 청크 ID·문단 번호는 사람이 읽기 어려워 쓰지 않는다."""
    return f"{chunk['title_ko']}({chunk['record_date'] or '총서'})"


def notebook_data(chunks):
    by_id = {c["chunk_id"]: c for c in chunks}
    parts, done = ss.goals, runtime.goals_done(ss.goals, ep.GOALS)
    goals = []
    for gid, goal in ep.GOALS.items():
        entries, pending = [], []
        for part in goal["parts"]:
            label = ep.PART_LABELS.get(part)
            entry = parts.get(part)
            if entry:   # 갈래 이름 + 미리 쓴 요약, 인물의 실제 말과 근거 기사는 펼쳐서 본다
                source = source_label(by_id[entry["source"]]) if entry["source"] in by_id else ""
                entries.append({"label": label, "summary": ep.PART_SUMMARIES.get(part, ""),
                                "who": entry["who"], "text": entry["text"], "cite": source})
            elif label:
                pending.append(label)
        goals.append({"id": gid, "title": goal["title"], "done": done[gid], "entries": entries, "pending": pending,
                      "count": len(entries), "total": len(goal["parts"]), "hint": goal["hint"]})
    marks = [{"who": m["who"], "q": m["q"], "a": view.strip_source_ids(m["a"])} for m in ss.marks]
    return {"goals": goals, "materials": material_groups(), "marks": marks,
            "focusWho": ss.who, "focus": focus_goal(ss.who, done)}


def focus_goal(who, done):
    """대화 상대가 맡은 목표 중 아직 확인 안 된 첫 목표(다 확인됐으면 첫 목표). 수첩은 상대가 바뀔 때 이것만 펼친다."""
    mine = [gid for gid, goal in ep.GOALS.items() if who in goal.get("people", ())]
    return next((gid for gid in mine if not done[gid]), mine[0] if mine else None)


def material_groups():
    """수첩 '자료' 탭: 근거로 확인된 기사를 목표 갈래별로 묶고(사용자 10-12 "안평대군과 결탁주장에 맞는 근거끼리 모아서"),
    답이 기댄 구절에 형광펜을 친다(근거 기사 창과 같은 표시). 한 기사가 여러 갈래의 근거면 각 갈래에 다 보인다."""
    found = {}   # 청크 ID → 카드(여러 답에서 나온 구절은 합침)
    for session in ss.talks.values():
        for turn in session.log:
            for card in (turn.evidence or {}).get("cards", []):
                item = found.setdefault(card["chunk_id"], {"title": card["title"], "date": card.get("record_date") or "총서",
                                                           "translation": card["translation"], "quotes": []})
                item["quotes"] += [q for q in card.get("quotes", []) if q not in item["quotes"]]
    groups, placed = [], set()
    for no, (gid, goal) in zip("①②③④⑤", ep.GOALS.items()):
        for part, sources in goal["parts"].items():
            ids = [cid for cid in sources if cid in found]
            if ids:
                groups.append({"label": f"{no} {goal['title']} · {ep.PART_LABELS.get(part, part)}", "items": ids})
                placed.update(ids)
    rest = [cid for cid in found if cid not in placed]
    if rest:
        groups.append({"label": "그 밖의 근거 기사", "items": rest})
    for group in groups:
        group["items"] = [{"title": found[c]["title"], "date": found[c]["date"],
                           "html": view.highlight_html(found[c]["translation"], found[c]["quotes"])} for c in group["items"]]
    return groups


def history_data():
    rows = []
    for item in ss.timeline:
        session = ss.talks.get(item["key"])
        if not session or item["index"] >= len(session.log):
            continue
        turn = session.log[item["index"]]
        rows.append({"scene": ep.SCENES[item["scene"]]["label"], "speaker": speaker_name(session, turn), "q": turn.user,
                     "a_html": " ".join(view.sentences_html(turn.answer, ep.INLINE_TERMS))})
    return rows


def suggested(chunks, who, scene, preview):
    """추천 질문(남은 것 전부, 보일 순서대로)과 한 번에 보일 개수. 이 인물에게 처음이면 넓은 질문 1개만,
    그 뒤로는 2개(사용자 10-12: 고를 것이 적어야 읽기 쉬움, 나머지는 화면의 '다른 질문 ↻'로).
    순서는 ① 방금 답이 근거로 삼은 문단의 꼬리 질문 → ② 아직 못 채운 목표 갈래의 질문 → ③ 나머지. 이미 물은 질문은 뺀다."""
    pool = ep.QUESTIONS[who] if who in ep.PEOPLE else ep.QUESTIONS[(ep.NARRATOR, scene)]
    # 이미 물은 질문, 그리고 겨냥한 목표 갈래가 이미 확인된 질문은 뺀다(10-12 리허설: 전균 질문 답에 '먼저 치고 뒤에 아뢴' 까닭이
    # 나와 1c가 확인됐는데도 "왜 전하께 먼저 아뢰지 않고…"를 추천함)
    left = [qid for qid, _ in pool if qid not in ss.asked and ep.QUESTION_PARTS.get(qid) not in ss.goals]
    order, limit = [], 2
    if who in ep.PEOPLE:
        session = talk(chunks, who, preview)
        limit = 1 if len(session.log) <= 1 else 2
        if len(session.log) > 1:
            last = session.log[-1]
            cited = [c["chunk_id"] for c in (last.evidence or {}).get("cards", [])] or list(last.context_ids or [])[:2]
            order += [q for cid in cited for q in ep.FOLLOW_UPS.get(cid, [])]
            order += [q for q in left if ep.QUESTION_PARTS.get(q) and ep.QUESTION_PARTS[q] not in ss.goals]
    text = dict(pool)
    picked = [q for q in dict.fromkeys(order + left) if q in left]
    return [{"qid": q, "text": text[q]} for q in picked], limit


def short_when(scene, base):
    """시간 이동 버튼에 쓸 짧은 날짜: '음력'을 빼고, 지금 장면과 같은 해면 해도 뺀다(1444년 음력 2월 21일 → 2월 21일)."""
    date = ep.SCENES[scene]["date"].replace("음력 ", "")
    year = ep.SCENES[base]["date"].split(" ")[0]
    return date[len(year) + 1:] if date.startswith(year + " ") else date


def stage_data(chunks, preview, problem):
    scene = ss.scene
    who = current_who()
    info = ep.SCENES[scene]
    done = runtime.goals_done(ss.goals, ep.GOALS)
    both = all(done[g] for g in list(ep.GOALS)[:-1])   # 인물에게 묻는 줄기(마지막 '뒤의 기록' 빼고)를 다 채웠나
    people = None
    if scene == 1:
        people = [{"name": name, "moment": person["moment"], "active": ss.who == name, "portrait": cutout(name)}
                  for name, person in ep.PEOPLE.items()]
    return {
        "assets": ui_assets(),
        "background": background(scene_bg(scene)),
        "title": ep.TITLE, "date": info["date"], "sceneLabel": info["label"], "scene": scene,
        "goal": ep.PEOPLE[who]["goal"] if who in ep.PEOPLE else info.get("goal", "배경과 뒤의 기록 확인하기"),
        "brief": {"intro": ep.INTRO, "items": [list(item) for item in ep.BRIEF_ITEMS], "note": ep.BRIEF_NOTE},
        "people": people,
        # 장면 2·3 가운데 안내 카드: 문장마다 줄을 바꾼다(사용자 10-12)
        "banner": [f"{info['where']} · {info['date']}", "이 장면에서는 해설자가 기록을 안내합니다.", ep.STAY_NOTE],
        # 입력칸 예시는 지금 대화 상대에 맞춘다(해설자 장면에 '왜 반대하셨나요?'가 보이던 것)
        "inputHint": "궁금한 것을 직접 물어도 돼요. 예: " + (ep.PEOPLE[who]["hint"] if who in ep.PEOPLE else ep.NARRATOR_HINT),
        "dialogue": dialogue_data(chunks, who, preview, scene),
        "failure": bool(ss.failure),
        "waitText": f"{who if who in ep.PEOPLE else '해설자'}의 답을 기다리고 있습니다",
        **dict(zip(("questions", "qLimit"), suggested(chunks, who, scene, preview))),
        "narratorChip": ("인물에게 돌아가기" if who == ep.NARRATOR else "해설자에게 묻기") if scene == 1 else None,
        "nextLabel": "다음 장면 →" if scene < 3 else "수첩 펼치기 →", "nextHi": both or scene >= 2,
        "nextWhen": short_when(scene + 1, scene) if scene < 3 else None, "backWhen": short_when(1, scene) if scene > 1 else None,
        "notebook": notebook_data(chunks), "memo": ss.get("memo", ""),
        "terms": [{"term": t, "desc": d} for t, d in ep.TERMS.items()],
        "history": history_data(),
        "settings": {"live": not preview, "problem": problem,
                     "measured": runtime.SETTINGS_LABEL + " · 인물별 허용 자료"},
    }


def episode_page(chunks):
    """취재 화면. 들어온 행동을 먼저 처리한 뒤(엔진 호출 포함) 화면 데이터를 내려보낸다."""
    action = ss.pop("pending", None)
    if action:
        preview, _ = live_mode(chunks)
        handle(chunks, preview, action)
        if ss.page != "episode":
            st.rerun()
    preview, problem = live_mode(chunks)
    with st.container(key="stagewrap"):
        stage.mount(stage_data(chunks, preview, problem), key=STAGE_KEY, on_action=on_stage_action, on_memo=on_stage_memo)


def finale(chunks):
    by_id = {c["chunk_id"]: c for c in chunks}
    done = runtime.goals_done(ss.goals, ep.GOALS)
    complete = all(done.values())
    st.html('<div class="page-head"><span class="eyebrow">취재 수첩을 펼치다</span><h1>이번 취재에서 확인한 것</h1>'
            f'<p>{"세 줄기를 모두 확인했습니다. 취재 완료!" if complete else "확인한 내용과 아직 남은 질문을 모았습니다. 이어서 취재할 수 있어요."}</p></div>')
    for gid, goal in ep.GOALS.items():
        with st.container(key=f"finale_{gid}"):
            st.html(f'<div class="finale-head">{"✓" if done[gid] else "○"} {goal["notebook"]}</div>')
            for part in goal["parts"]:
                entry = ss.goals.get(part)
                if entry:   # 갈래 이름·요약을 먼저, 인물의 실제 말과 근거 기사는 작게
                    st.markdown(f"**✓ {ep.PART_LABELS.get(part, '')}** · {ep.PART_SUMMARIES.get(part, '')}")
                    source = source_label(by_id[entry["source"]]) if entry["source"] in by_id else ""
                    st.caption(" · ".join(x for x in (f"{entry['who']}: “{entry['text']}”", source) if x))
            if not done[gid]:
                st.caption(f"남은 질문 · {goal['hint']}")
    if ss.get("memo"):
        st.html('<div class="finale-head">내 메모</div>')
        st.write(ss.memo)
    a, b, _ = st.columns([1, 1, 2])
    a.button("더 취재하기", key="finale_more", on_click=go, args=("episode",), kwargs={"scene": 1})
    b.button("처음으로", key="finale_home", on_click=go, args=("home",))


# 카드·문제·실록에 묻기·마무리 화면의 배경(10-12 사용자 "배경 추가"). 어둡게 덮어 글씨가 먼저 보이게 한다
# 화면 전용 그림(앞)이 assets/에 없으면 있는 그림(뒤)을 빌려 쓴다. 새 그림은 같은 이름으로 넣기만 하면 바뀐다(10-12 사용자 "새로 뽑자")
PAGE_BACKDROPS = {"modes": ("bg_select", "bg_home"), "events": ("bg_select", "bg_home"), "quiz": ("bg_quiz", "bg_record"),
                  "archive": ("bg_archive", "bg_record"), "finale": ("bg_finale", "bg_record")}
NARROW_PAGES = ("quiz", "archive", "finale")   # 읽는 화면은 가운데 좁은 칸에(넓은 창에서 왼쪽에 몰려 보이던 것)


def pick_asset(*names):
    """assets/에 있는 첫 그림 이름(하나도 없으면 마지막 이름, 그때는 background()가 SVG로 대신함)."""
    return next((n for n in names if (ASSETS / f"{n}.png").exists()), names[-1])


def scene_bg(scene):
    """장면 n의 배경(BACKGROUNDS의 n번째, 모자라면 마지막 것). 사건 그림이 없으면 바로 앞 장면 것 → 언문 논쟁 배경을 빌림."""
    names = list(ep.BACKGROUNDS[:scene])[::-1]
    return pick_asset(*names, "bg_scene1" if scene == 1 else "bg_record")


def page_backdrop(page):
    names = PAGE_BACKDROPS.get(page)
    if names:
        name = pick_asset(*names)
        st.html(f"<style>.stApp{{background-image:linear-gradient(180deg,rgba(9,14,22,.80),rgba(9,14,22,.94)),{backdrop(name)};"
                "background-size:cover;background-position:center;background-attachment:fixed}</style>")


def warm_assets():
    """화면이 쓰는 그림을 모두 줄여 assets/sized/에 두고, 없는 원본 이름을 돌려주며 터미널에 알린다.

    캐시가 없으면 화면마다 처음 들어갈 때 1-2초씩 늦던 것을 한 번에 한다(10-13 사용자 "없는지 먼저 체크하는게 낫지").
    그림이 없어도 화면은 대체 그림으로 뜨므로 빠진 것을 여기서만 알 수 있다.
    """
    jobs = [(asset_png, name, width) for name, width in UI_ASSETS.items()] + [(asset_uri, "icon_narrator", 96)]
    cards = ["card_mode_interview", "card_mode_ask_closed", "card_mode_ask", "card_mode_quiz"]   # modes()의 카드
    backs = {"bg_home"} | {name for names in PAGE_BACKDROPS.values() for name in names}
    for module in episodes.EPISODES.values():
        cards.append(module.CARD["img"])
        backs.update(module.BACKGROUNDS)
        for file in module.PORTRAITS.values():
            jobs += [(asset_uri, file, 520), (asset_png, file + "_cut", 520)]
    jobs += [(asset_uri, name, 560) for name in cards] + [(asset_uri, name, 1600) for name in sorted(backs)]
    missing = [name for make, name, width in jobs if make(name, width) is None]
    if missing:
        print("[역사 취재록] ui/assets/에 없는 그림(대체 그림으로 보임):", ", ".join(missing))
    return missing


def _warm_up():
    warm_assets()
    runtime.live_problem(load_chunks())   # 검색 DB를 처음 여는 데 1.5초 안팎(chromadb 불러오기 포함)


@st.cache_resource
def start_warm_up():
    """서버를 켠 뒤 첫 접속 때 한 번, 그림 캐시와 검색 DB 준비를 뒤에서 시작한다(기다리지 않음).

    첫 화면은 이것을 기다리지 않고 바로 뜨고, 시작하기를 누를 즈음이면 끝나 있다. 그보다 먼저 DB 확인이
    필요하면 남은 시간만 기다린다(10-13 사용자 "모드 선택이나 그런건 미리 띄우고 뒤에서 그런 준비 작업 하면 되잖음").
    """
    worker = threading.Thread(target=_warm_up, name="warm-up", daemon=True)
    worker.start()
    return worker


def page_body(chunks, preview):
    if ss.page == "modes":
        modes()
    elif ss.page == "events":
        events()
    elif ss.page == "finale":
        finale(chunks)
    elif ss.page in EXTRA_PAGES:
        view.glossary_drawer()
        EXTRA_PAGES[ss.page][2](chunks, preview)


def main():
    global ep
    start_warm_up()
    init_state()
    chunks = chunks_all()
    handle_pick()
    ep = episodes.EPISODES[ss.episode]
    if ss.page == "home":
        home()   # 첫 화면은 실제 답변 확인(검색 DB)이 필요 없어 기다리지 않는다
        return
    preview, problem = live_mode(chunks)
    if ss.page == "episode":
        episode_page(chunks)   # 취재 화면은 컴포넌트가 머리·메뉴까지 직접 그린다
        return
    topbar(problem)
    if ss.page == "briefing":
        st.html(f"<style>.st-key-briefing{{background-image:linear-gradient(180deg,rgba(10,18,28,.72),rgba(10,18,28,.94)),{backdrop(scene_bg(1))}}}</style>")
        briefing()
        return
    page_backdrop(ss.page)
    if ss.page in NARROW_PAGES:
        with st.container(key="pagebody"):
            page_body(chunks, preview)
    else:
        page_body(chunks, preview)


if __name__ == "__main__":
    main()
