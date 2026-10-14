"""조건 C·D1·D2로 한 번의 질문 또는 여러 턴 대화를 처리한다.

- C: 이번 사용자 발화로 번역문 청크를 검색해 넣는다. 인물 역할이면 장면 설정 문장도 검색기(임베딩)·리랭커에 함께 준다
  (지시어·"오늘 상소"가 다른 기사를 찾던 B1·C1·B9, 작업기록 [183]). 앞선 대화는 검색에 넣지 않는다(사관의 틀린 전제가 검색어로 들어감).
- D1: C와 같지만 인물 역할일 때 장면 시점(cutoff, 예: "1444-02-20") 뒤에 알려진 청크와 '후일 기록' 청크(사론·졸기 등)를
  검색 대상에서 뺀다(청크의 known_from 기준).
- D2: D1 + 역할 밖 요청은 해설자가 따로 답하고, 그 문답은 인물의 대화 이력에 넣지 않는다.
"""
import json
import re
from dataclasses import dataclass, field

from . import config
from .corpus import known_key

OUT_OF_ROLE = re.compile(r"역할(을|에서)?\s*(잠깐\s*)?(벗|내려|빠져)|실제\s*역사|해설(자|해)")


def is_out_of_role(text: str) -> bool:
    return bool(OUT_OF_ROLE.search(text))


@dataclass
class TurnResult:
    user: str
    answer: str
    speaker: str                 # 답한 쪽: "character"(인물) | "narrator"(해설자) | "assistant"(일반 도우미)
    context_ids: list[str]
    retrieved: list[dict] = field(default_factory=list)   # 검색된 청크 목록 [{chunk_id, score}]
    messages: list[dict] = field(default_factory=list)
    check: str | None = None          # 3차: 답변에 메모로 넘긴 전제 판정(--rerank-check를 켰을 때만)
    rerank_trace: dict | None = None  # 리랭커 단계 기록(후보 ID·모델이 고른 ID·대체 여부). 리랭커가 없으면 None
    search_scene: bool = False        # 검색에 장면 설정을 함께 줬나(인물 역할 턴)
    evidence: dict | None = None      # 근거 보기 내용(evidence.annotate). 따로 요청했을 때만 만든다(호출 1번 추가)


class ChatSession:
    def __init__(self, condition: str, chunks: list[dict], llm, retriever=None,
                 mode: str = "fact", character: str | None = None, setting: str | None = None,
                 cutoff: str | None = None, top_k: int = config.TOP_K,
                 known_facts: list[dict] | None = None):
        if condition not in config.CONDITIONS:
            raise ValueError(f"알 수 없는 조건: {condition}")
        if retriever is None:
            raise ValueError("검색기가 필요합니다.")
        self.condition = condition
        self.chunks = chunks
        self.llm = llm
        self.retriever = retriever
        self.mode = mode
        self.character = character
        self.setting = setting
        self.cutoff = cutoff                  # 장면 시점. 예: "1444-02-20", 같은 날 오후면 "1444-02-20 오후"
        self.top_k = top_k
        self.known_facts = known_facts or []   # 인물 역할일 때 매 턴 시스템 프롬프트에 넣는 '이미 아는 사실' 카드
        self.log: list[TurnResult] = []

    # 인물(또는 도우미)이 보는 이전 대화. D2에서는 해설자 문답을 뺀다.
    def _history_for(self, speaker: str) -> list[dict]:
        msgs = []
        for t in self.log:
            if self.condition == "D2" and speaker == "character" and t.speaker == "narrator":
                continue
            msgs.append({"role": "user", "content": t.user})
            msgs.append({"role": "assistant", "content": t.answer})
        return msgs

    def _scene(self, speaker: str) -> str | None:
        """인물이 답하는 턴이면 검색에 같이 줄 장면 설정 문장. 해설자·일반 질문은 없음."""
        return self.setting if self.mode == "role" and speaker == "character" and self.setting else None

    def _context(self, query: str, speaker: str) -> tuple[list[dict], list[dict]]:
        use_cutoff = self.condition in ("D1", "D2") and self.mode == "role" and speaker == "character"
        cutoff = known_key(self.cutoff) if use_cutoff and self.cutoff else None
        scene = self._scene(speaker)
        hits = self.retriever.search(query, self.top_k, cutoff, **({"scene": scene} if scene else {}))
        retrieved = [{"chunk_id": c["chunk_id"], "score": round(s, 4)} for c, s in hits]
        return [c for c, _ in hits], retrieved

    def evidence_for(self, index: int, llm=None, lookup: dict | None = None) -> dict:
        """index번째 턴에 근거 보기 내용을 붙인다(답변 모델 호출 1번 추가, 작업기록 [196]).
        인물 턴은 아는 사실 카드와 그 인물의 앞선 답도 근거로 본다. 해설자 사실 근거만."""
        from .evidence import annotate

        t = self.log[index]
        by_id = {c["chunk_id"]: c for c in self.chunks}
        ctx = [by_id[cid] for cid in t.context_ids if cid in by_id]
        is_char = t.speaker == "character"
        prior = [x.answer for x in self.log[:index] if x.speaker == "character"] if is_char else None
        t.evidence = annotate(llm or self.llm, t.answer, ctx, self.known_facts if is_char else None, prior,
                              lookup or by_id)
        return t.evidence

    def ask(self, user_text: str) -> TurnResult:
        from .prompts import premise_note, system_prompt

        if self.mode != "role":
            speaker = "assistant"
        elif self.condition == "D2" and is_out_of_role(user_text):
            speaker = "narrator"
        else:
            speaker = "character"

        history = self._history_for(speaker)
        ctx, retrieved = self._context(user_text, speaker)
        # 3차: 리랭커가 '틀림'으로 판정한 전제(근거 확인된 것만)를 답변에 메모로 붙인다. 해설자는 뺀다.
        premise = None if speaker == "narrator" else getattr(self.retriever, "last_premise", None)
        prompt_mode = {"assistant": "fact", "character": "role", "narrator": "narrator"}[speaker]
        system = system_prompt(prompt_mode, ctx, self.character, self.setting, self.known_facts)
        last_user, check = user_text, None
        if premise:
            check = json.dumps(premise, ensure_ascii=False)
            last_user = f"{user_text}\n\n" + premise_note(premise)
        messages = [{"role": "system", "content": system}, *history,
                    {"role": "user", "content": last_user}]
        answer = self.llm.chat(messages)
        result = TurnResult(user_text, answer, speaker, [c["chunk_id"] for c in ctx], retrieved, messages, check,
                            getattr(self.retriever, "last_trace", None), self._scene(speaker) is not None)
        self.log.append(result)
        return result
