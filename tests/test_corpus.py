import re
from collections import Counter

from sillok_rag.corpus import han_only, known_key, load_articles, load_chunks
from sillok_rag.evaluate import load_all_scenarios, load_questions, load_scenarios

chunks = load_chunks()
by_id = {c["chunk_id"]: c for c in chunks}
PETITION = "wda_12602020_001"   # 최만리 등의 상소와 세종의 논박(2월 20일 기사)


def test_every_article_is_chunked_without_losing_text():
    """기사 132건이 모두 청크로 들어 있고, 원문 한자가 거의 그대로 덮인다.
    정제 규칙(날짜 간지 삭제, 교감 글자 반영, 사론을 끝으로)으로 달라지는 글자는 기사당 몇 자뿐이다.
    문장 하나가 통째로 빠지면 여기서 걸린다."""
    by_article: dict[str, list[dict]] = {}
    for c in chunks:
        by_article.setdefault(c["article_id"], []).append(c)
    articles = load_articles()
    assert len(articles) == 132 and set(by_article) == {a["article_id"] for a in articles}
    for a in articles:
        # 권 끝 표시(…實錄卷第…終, 문단 끝에 붙은 …日記卷第…)는 정제 규칙 R13으로 지운다(규칙서 v2 ⑫)
        text = "".join(re.sub(r"\S{2,8}日記卷第[一二三四五六七八九十百]+終?$", "", p) for p in a["paragraphs"] if "實錄卷" not in p)
        full = Counter(han_only(text))
        joined = Counter(han_only("".join(c["original"] for c in by_article[a["article_id"]])))
        assert sum((full - joined).values()) <= 10, a["article_id"]
        assert sum((joined - full).values()) <= 15, a["article_id"]


def test_every_chunk_has_translation_speaker_and_time():
    assert len(chunks) == 803 and len(by_id) == 803   # 규칙서 v2 (v1.1은 793, v2 처음 804 → 검사표 v2로 1곳 합침)
    for c in chunks:
        assert c["translation"].strip() and c["translation_status"] == "ai_draft", c["chunk_id"]
        assert c["speaker"], c["chunk_id"]
        assert c["known_from"], c["chunk_id"]


def test_known_key_orders_dates():
    assert known_key("1444-02-20 이전") < known_key("1444-02-20") < known_key("1444-02-20 오후") < known_key("1444-02-21")
    assert known_key("1443-12") < known_key("1443-12-30")
    assert known_key("1795-02-30") < known_key("1795-윤02-12") < known_key("1795-03-01")
    # 범위는 끝으로 연다(규칙서 v2): 여러 해에 걸친 배경이 시작 해의 장면에 새지 않게
    assert known_key("1392~1398") == known_key("1398-12-31")
    assert known_key("1592-05-06~05-29") == known_key("1592-05-29")
    assert known_key("1592-05-29~07-06") == known_key("1592-07-06")
    assert known_key("1476~1504 (세자 시절)") == known_key("1504-12-31")
    assert known_key("후일 기록(사론)") is None and known_key(None) is None
    assert known_key("인물 모름(사론)") is None   # 2026-09-30 전 이름(옛 결과 파일)


def test_same_day_afternoon_comes_after_the_petition():
    """상소(오전)와 세종의 논박·하옥(오후)은 같은 2월 20일이지만, 상소 직후 장면에서는 논박·하옥을 모른다."""
    petition = [by_id[f"{PETITION}-{n:02d}"]["known_key"] for n in range(1, 9)]
    afternoon = [by_id[f"{PETITION}-{n:02d}"]["known_key"] for n in (9, 10, 11, 12, 14)]
    assert max(petition) < min(afternoon)


def test_next_day_part_of_feb20_article_is_split_out():
    nxt = [c for c in chunks if c["article_id"] == PETITION and "翌日" in c["original"]]
    assert len(nxt) == 1
    jail = [c for c in chunks if "趙瑾于義禁府" in c["original"]]
    assert nxt[0]["known_key"] > max(c["known_key"] for c in jail)
    # 김문 국문 전지(10문단)도 다음 날 조각에 함께 있다 (청크의 문단 번호는 0부터)
    assert 9 in nxt[0]["paragraphs"]


def test_petition_says_27_letters():
    assert any("二十七字諺文" in c["original"] and "27자" in c["translation"] for c in chunks)


def test_eval_v3_matches_corpus():
    """평가셋 v3의 정답 청크가 코퍼스에 있고, 핵심어(must_terms)가 정답 청크 번역에 나온다.
    번역을 고치면 여기서 짝이 어긋난 문항을 알려 준다(맞게 답해도 자동 채점에서 틀리게 나오는 것을 막기)."""
    for q in load_questions():
        for cid in q.get("gold_chunks", []) + q.get("near_chunks", []):
            assert cid in by_id, (q["id"], cid)
        gold = " ".join(by_id[cid]["translation"] for cid in q.get("gold_chunks", []))
        if not gold:
            continue   # 자료 없음·다른 시대 함정은 정답 청크가 없다
        for term in q.get("must_terms", []):
            assert any(alt in gold for alt in term.split("|")), (q["id"], term)


_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_NARR_DATE = re.compile(r"(?:([一二三四五六七八九十]{1,2})月)?(?:初([一二三四五六七八九十])|([一二三四五六七八九十廿]{1,3}))日")


def _cn(s: str) -> int:
    s = s.replace("廿", "二十")
    if "十" in s:
        a, _, b = s.partition("十")
        return (_NUM.get(a, 1) if a else 1) * 10 + (_NUM.get(b, 0) if b else 0)
    return _NUM.get(s, 0)


# 원문 날짜가 알게 되는 때보다 뒤지만 사건이 아닌 것(사람이 확인함, 2026-09-30)
_DATE_OK = {
    "wda_11811001_005-05": "十一月十日: '11월 10일 이전까지 지킨다'는 계절 기준",
    "wra_10703025_006-12": "己亥五月初六日: 7년 전(1659)을 회상",
}


def test_narration_dates_are_not_after_known_from():
    """서술(따옴표·【】 밖)에 적힌 날짜가 '알게 되는 때'보다 뒤면 미래 정보가 샌다(한산도 기사처럼 여러 날을 모은 청크).
    2026-09-30 무작위 확인에서 사람이 찾은 유형을 기계로 전체 검사한다(작업기록 [118])."""
    bad = []
    for c in chunks:
        k = c["known_key"]
        if k is None or c["chunk_id"] in _DATE_OK:
            continue
        kmon, kday = int(k) // 100 % 100, int(k) % 100
        text = re.sub(r"\"[^\"]*\"|“[^”]*”|‘[^’]*’|【[^】]*】", "", c["original"])
        mon = kmon
        for m in _NARR_DATE.finditer(text):
            if m.group(1):
                mon = _cn(m.group(1))
            day = _cn(m.group(2) or m.group(3))
            if not (1 <= day <= 30) or m.group() == "一日" or mon - kmon >= 6 or kmon - mon >= 6:
                continue
            if (mon, day) > (kmon, kday or 99):
                bad.append((c["chunk_id"], c["known_from"], m.group()))
    assert not bad, bad


def test_month_only_known_from_is_only_for_this_month_articles():
    """알게 되는 때를 달만 적으면(1801-01) 그 달 1일부터 보인다. 是月(이달) 기사나 날짜 없는 총서에만 쓴다.
    先是·初·前此 배경은 '기사 날짜 이전'으로 적는다(규칙서 v2, 작업기록 [118])."""
    this_month = {c["article_id"] for c in chunks if c["original"].startswith("是月")}
    bad = [(c["chunk_id"], c["known_from"]) for c in chunks
           if re.fullmatch(r"\d{4}-\d{2}", (c["known_from"] or "").strip())
           and c["record_date"] and c["article_id"] not in this_month]
    assert not bad, bad


def test_scenario_cards_point_to_existing_chunks():
    for sc in load_all_scenarios().values():
        assert known_key(sc["cutoff"]) is not None
        for f in sc.get("known_facts", []):
            assert f["source"] in by_id, f["source"]


def test_gyeyu_scenarios_are_new_and_answerable_at_cutoff():
    """두 번째 사건 시나리오 D·E(작업기록 [188]): 정답 청크가 코퍼스에 있고 그 장면 시점에 인물이 알 수 있으며,
    개발에 쓴 평가 문항(v3·검증셋)과 질문이 겹치지 않는다(ChatGPT와 새 문항으로 비교하기 위함).
    사육신 기사는 6청크뿐이라 정답 청크는 개발 문항과 겹칠 수 있다(E1·E2 ↔ T03의 -02, E5·E8 ↔ F11의 -06). 겹침은 이 목록으로 고정한다."""
    from sillok_rag import config

    used = {c for s in ("v3", HOLDOUT, HOLDOUT_B) for q in load_questions(s) for c in q.get("gold_chunks", [])}
    asked = {q["question"] for s in ("v3", HOLDOUT, HOLDOUT_B) for q in load_questions(s)}
    scs = load_scenarios(config.SCENARIOS_GYEYU_PATH)
    overlap = set()
    assert set(scs) == {"D", "E"} and not set(scs) & set(load_scenarios())
    for sc in scs.values():
        cut = known_key(sc["cutoff"])
        assert len(sc["turns"]) == 10
        for t in sc["turns"]:
            assert t["user"] not in asked
            for cid in t.get("gold_chunks", []):
                assert cid in by_id, (t["id"], cid)
                if cid in used:
                    overlap.add(t["id"])
                assert by_id[cid]["known_key"] is not None and by_id[cid]["known_key"] <= cut, (t["id"], cid)
            assert t.get("gold_chunks") or t.get("leak_terms"), t["id"]
    assert overlap == {"E1", "E2", "E5", "E8"}


HOLDOUT = "holdout_v1_20260930"
HOLDOUT_B = "holdout_v1b_20260930"   # 같은 사실을 키워드(인물·용어)를 빼고 두루뭉술하게 물은 벌


def test_holdout_matches_corpus_and_does_not_overlap_v3():
    """검증셋 v1(처음 보는 문항)도 정답 청크·핵심어가 코퍼스와 맞고, v3와 한능검 문항·근거 기사가 겹치지 않는다
    (v3는 반복 개선에 쓴 개발셋이라, 겹치면 검증이 되지 않음. 재료 나누기는 docs/기록/평가셋/검증재료_나누기_20260930.csv)."""
    v3 = load_questions()
    ho = load_questions(HOLDOUT)
    v3_hn = {h for q in v3 for h in q.get("hanneung", [])}
    v3_art = {c.rsplit("-", 1)[0] for q in v3 for c in q.get("gold_chunks", []) + q.get("near_chunks", [])}
    assert len(ho) == 24 and len({q["id"] for q in ho}) == 24
    for q in ho:
        assert not set(q["hanneung"]) & v3_hn, q["id"]
        for cid in q.get("gold_chunks", []) + q.get("near_chunks", []):
            assert cid in by_id, (q["id"], cid)
            assert cid.rsplit("-", 1)[0] not in v3_art, (q["id"], cid)
        gold = " ".join(by_id[cid]["translation"] for cid in q.get("gold_chunks", []))
        for term in q.get("must_terms", []) if gold else []:
            assert any(alt in gold for alt in term.split("|")), (q["id"], term)


HOLDOUT_V2 = "holdout_v2_20261008"   # 최종 측정에 한 번 쓴 홀드아웃(작업기록 [330]-[331])


def test_holdout_v2_is_locked_and_matches_corpus():
    """홀드아웃 v2는 잠근 그대로이고(sha256 앞 12자리, [330]), 정답 청크가 코퍼스에 있고, 개발셋 v3·검증셋 v1과
    근거 기사가 겹치지 않는다. 근거 있는 17문항은 서로 다른 기사 17건이다(코드정리검토 C23·X31)."""
    import hashlib

    from sillok_rag import config

    raw = (config.EVAL_DIR / f"{HOLDOUT_V2}.jsonl").read_bytes().replace(b"\r\n", b"\n")   # Windows 줄바꿈 변환 무시
    assert hashlib.sha256(raw).hexdigest()[:12] == "a99936f3866e"
    v2 = load_questions(HOLDOUT_V2)
    assert len(v2) == 20 and len({q["id"] for q in v2}) == 20
    used = {c.rsplit("-", 1)[0] for s in ("v3", HOLDOUT) for q in load_questions(s)
            for c in q.get("gold_chunks", []) + q.get("near_chunks", [])}
    gold_articles = []
    for q in v2:
        cids = q.get("gold_chunks", []) + q.get("near_chunks", [])
        for cid in cids:
            assert cid in by_id, (q["id"], cid)
            assert cid.rsplit("-", 1)[0] not in used, (q["id"], cid)
        if q["abstain"]:
            assert not cids, q["id"]
        gold = " ".join(by_id[cid]["translation"] for cid in q.get("gold_chunks", []))
        for term in q.get("must_terms", []) if gold else []:
            assert any(alt in gold for alt in term.split("|")), (q["id"], term)
        if q.get("gold_chunks"):
            gold_articles.append({c.rsplit("-", 1)[0] for c in q["gold_chunks"]})
    assert len(gold_articles) == 17 and len(set().union(*gold_articles)) == 17


def test_holdout_b_differs_only_in_question():
    """두 벌은 질문 문장만 다르고 번호·기대 답·정답 청크는 같다(두 벌의 점수 차이 = 질문 표현의 영향)."""
    a, b = load_questions(HOLDOUT), load_questions(HOLDOUT_B)
    assert [q["id"] for q in a] == [q["id"] for q in b]
    for qa, qb in zip(a, b):
        assert qa["question"] != qb["question"], qa["id"]
        assert {k: v for k, v in qa.items() if k != "question"} == {k: v for k, v in qb.items() if k != "question"}
