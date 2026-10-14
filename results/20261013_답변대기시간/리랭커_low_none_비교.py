"""리랭커 생각 수준 low(측정 설정) vs none: 시간·고른 자료·전제 판정(실제 API, 유료). 저장소 코드는 바꾸지 않음."""
import sys, time
sys.path.insert(0, ".")
from sillok_rag import config
from sillok_rag.llm import LLM
from sillok_rag.corpus import load_chunks
from ui import runtime, episode, episode_gyeyu

times = []
_chat = LLM.chat
def chat(self, messages, json_mode=False):
    t = time.perf_counter(); before = dict(self.usage)
    out = _chat(self, messages, json_mode)
    times.append((self.reasoning_effort, json_mode, time.perf_counter() - t,
                  self.usage["completion"] - before["completion"], self.usage["reasoning"] - before["reasoning"]))
    return out
LLM.chat = chat

chunks = load_chunks()
runtime.live_problem(chunks)
cases = [("최만리", episode, episode.QUESTIONS["최만리"][0][1]),
         ("수양대군", episode_gyeyu, episode_gyeyu.QUESTIONS["수양대군"][0][1]),
         ("실록에 묻기(함정 H2T01)", None, runtime.FACT_QUESTIONS[1])]
for name, ep, q in cases:
    print(f"\n== {name}: {q}")
    for effort in ("low", "none"):
        rer = LLM(model=config.RERANK_MODEL, reasoning_effort=effort)
        if ep:
            s = runtime.open_interview(chunks, name, preview=False, ep=ep, rerank_llm=rer)
        else:
            s = runtime.create_session(chunks, preview=False, rerank_llm=rer)
        times.clear()
        t = time.perf_counter(); turn = runtime.ask_nonempty(s, q); total = time.perf_counter() - t
        r = [x for x in times if x[1]][0]; a = [x for x in times if not x[1]][0]
        print(f"  [{effort}] 리랭커 {r[2]:.1f}s(출력{r[3]}, 생각{r[4]}) 답변 {a[2]:.1f}s  합계 {total:.1f}s")
        print(f"     고른 자료: {turn.context_ids}")
        print(f"     전제 판정 메모: {turn.check!r}")
        print(f"     답: {turn.answer[:160]!r}")
