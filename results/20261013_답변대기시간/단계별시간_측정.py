"""질문 하나의 단계별 시간(실제 API, 유료). 저장소 코드는 바꾸지 않고 LLM 호출만 감싸 잰다."""
import sys, time
sys.path.insert(0, ".")
from sillok_rag.llm import LLM
from sillok_rag.corpus import load_chunks
from ui import runtime, episode, episode_gyeyu

calls = []
_chat, _embed = LLM.chat, LLM.embed
def chat(self, messages, json_mode=False):
    t = time.perf_counter(); before = dict(self.usage)
    out = _chat(self, messages, json_mode)
    calls.append(("chat", self.model, self.reasoning_effort, json_mode, time.perf_counter() - t,
                  self.usage["prompt"] - before["prompt"], self.usage["completion"] - before["completion"],
                  self.usage["reasoning"] - before["reasoning"]))
    return out
def embed(self, texts):
    t = time.perf_counter(); out = _embed(self, texts)
    calls.append(("embed", self.embed_model, None, False, time.perf_counter() - t, 0, 0, 0)); return out
LLM.chat, LLM.embed = chat, embed

chunks = load_chunks()
runtime.live_problem(chunks)
for ep, who in ((episode, "최만리"), (episode_gyeyu, "수양대군")):
    qid, q = ep.QUESTIONS[who][0]
    s = runtime.open_interview(chunks, who, preview=False, ep=ep)
    calls.clear()
    t = time.perf_counter(); runtime.ask_and_check(s, q, False); total = time.perf_counter() - t
    print(f"\n== {who}: {q}\n총 {total:.1f}s")
    for c in calls:
        print(f"  {c[0]:5s} {c[1]} effort={c[2]} json={c[3]}  {c[4]:.1f}s  입력{c[5]} 출력{c[6]}(생각{c[7]})")
    calls.clear()
    low = LLM(reasoning_effort="low")
    s.log[-1].evidence = None
    t = time.perf_counter(); ev = s.evidence_for(len(s.log) - 1, llm=low)
    print(f"  [비교] 근거 대조 low: {time.perf_counter() - t:.1f}s  출력{calls[-1][6]}(생각{calls[-1][7]})  문장 {len(ev.get('segments', []))}개")
