"""근거 보기(evidence.py): 표시 확인 규칙과 기사 카드(작업기록 [196])."""
import json

from sillok_rag.chat import ChatSession
from sillok_rag.corpus import load_chunks
from sillok_rag.evaluate import is_result_file, load_scenarios
from sillok_rag.evidence import annotate, verify
from sillok_rag.retrieval import BM25Retriever

chunks = load_chunks()
by_id = {c["chunk_id"]: c for c in chunks}
C05 = by_id["wda_12602020_001-05"]   # 상소 속 '27자 언문'
ANSWER = "그렇지 않소. 상소에는 27자 언문이라 썼소. 이는 학문이 쇠할까 염려한 뜻이오. 물으시오."


class ReplyLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat(self, messages, json_mode=False):
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return json.dumps(self.reply, ensure_ascii=False)


def seg(text, label, source="", quote=""):
    return {"text": text, "label": label, "source": source, "quote": quote}


def test_record_needs_quote_that_really_is_in_the_chunk():
    segs = verify([seg("상소에는 27자 언문이라 썼소.", "기록", C05["chunk_id"], "27자 언문"),
                   seg("이는 학문이 쇠할까 염려한 뜻이오.", "기록", C05["chunk_id"], "학문이 쇠할까 염려")],
                  ANSWER, [C05])
    assert segs[0]["label"] == "기록" and segs[0]["verified"]
    # 근거 구절이 번역문에 없으면 기록을 떼고 해석으로(화면에 없는 출처를 보여 주지 않음)
    assert segs[1]["label"] == "해석" and not segs[1]["verified"] and segs[1]["quote"] == ""


def test_quote_matches_without_hanja_in_parentheses():
    """번역문은 '부제학(副提學) 최만리(崔萬理)'처럼 한자를 병기한다. 모델이 한자를 빼고 옮겨도 같은 구절로 본다."""
    c01 = by_id["wda_12602020_001-01"]
    answer = "부제학 최만리 등이 상소하였소."
    segs = verify([seg("부제학 최만리 등이 상소하였소.", "기록", c01["chunk_id"], "부제학 최만리 등이 상소하기를")], answer, [c01])
    assert segs[0]["label"] == "기록" and segs[0]["verified"]


def test_segments_must_copy_the_answer_and_fiction_has_no_source():
    segs = verify([seg("상소에는 28자라고 썼소.", "기록", C05["chunk_id"], "27자 언문"),   # 답변에 없는 글
                   seg("물으시오.", "창작", C05["chunk_id"], "27자 언문"),
                   seg("이는 학문이 쇠할까 염려한 뜻이오.", "해석", "없는ID"),
                   seg("그렇지 않소.", "모름")],
                  ANSWER, [C05])
    assert [s["text"] for s in segs] == ["물으시오.", "이는 학문이 쇠할까 염려한 뜻이오."]
    assert segs[0]["source"] == "" and segs[0]["quote"] == ""
    assert segs[1]["source"] == ""


def test_button_only_when_a_verified_record_exists_and_card_shows_the_article():
    ev = annotate(ReplyLLM({"segments": [seg("상소에는 27자 언문이라 썼소.", "기록", C05["chunk_id"], "27자 언문"),
                                          seg("물으시오.", "창작")]}), ANSWER, [C05])
    assert ev["show_button"] and len(ev["cards"]) == 1
    card = ev["cards"][0]
    assert card["chunk_id"] == C05["chunk_id"] and card["quotes"] == ["27자 언문"]
    assert card["original"] == C05["original"] and card["url"].startswith("http")
    ev = annotate(ReplyLLM({"segments": [seg("물으시오.", "창작")]}), ANSWER, [C05])
    assert not ev["show_button"] and ev["cards"] == []
    ev = annotate(ReplyLLM(RuntimeError("x")), ANSWER, [C05])
    assert not ev["show_button"] and ev["error"] == "RuntimeError"


def test_known_fact_card_is_record_but_own_earlier_answer_is_not():
    """카드는 실록 근거라 기록, 인물의 앞선 답은 실록이 아니라 해석으로 내린다([204]). 시점은 근거를 비운다."""
    sc = load_scenarios()["B"]
    fact = sc["known_facts"][0]
    answer = "그렇지 않소. 오늘 상소에 이름을 올린 이는 일곱 사람이오. 내가 앞서 말한 대로요. 그 뒤의 일은 알지 못하오."
    ev = annotate(ReplyLLM({"segments": [
        seg("오늘 상소에 이름을 올린 이는 일곱 사람이오.", "기록", "카드", fact["fact"][:20]),
        seg("내가 앞서 말한 대로요.", "기록", "앞선 답", "상소를 올린 까닭"),
        seg("그 뒤의 일은 알지 못하오.", "시점", "앞선 답", "알지 못하오")]}),
        answer, [], sc["known_facts"], ["오늘 상소를 올린 까닭은 학문 때문이오."], by_id)
    assert [(s["label"], s["verified"]) for s in ev["segments"]] == [("기록", True), ("해석", False), ("시점", False)]
    assert ev["segments"][1]["source"] == "앞선 답" and ev["segments"][1]["quote"] == ""
    assert ev["segments"][2]["source"] == "" and ev["segments"][2]["quote"] == ""
    assert [c["chunk_id"] for c in ev["cards"]] == [fact["source"]]   # 카드의 근거 청크로 기사 카드


def test_session_evidence_uses_character_history_and_result_files_skip_evidence():
    sc = load_scenarios()["A"]

    class Echo:
        model, dry_run, embed_model = "fake", True, "fake"

        def chat(self, messages, json_mode=False):
            return "답변"

    s = ChatSession("D2", chunks, Echo(), BM25Retriever(chunks), mode="role", character=sc["character"],
                    setting=sc["setup"], cutoff=sc["cutoff"], known_facts=sc["known_facts"])
    s.ask("첫 질문")
    s.ask("두 번째 질문")
    llm = ReplyLLM({"segments": []})
    s.evidence_for(1, llm)
    user = llm.calls[0][1]["content"]
    assert "[아는 사실]" in user and "[앞선 답]\n- 답변" in user and s.log[1].evidence["show_button"] is False
    from pathlib import Path
    assert not is_result_file(Path("x_scenarioA.evidence.jsonl")) and is_result_file(Path("x_scenarioA.jsonl"))
