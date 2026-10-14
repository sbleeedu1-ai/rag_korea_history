"""OpenAI 호출을 한곳에 모은다. dry_run이면 API를 부르지 않는다."""
import os

from dotenv import load_dotenv

from . import config

# 프로젝트 폴더의 .env 파일에서 OPENAI_API_KEY를 읽는다. (.env는 git에 올리지 않음)
load_dotenv(config.ROOT / ".env")

EMBED_BATCH = 100   # 임베딩 한 요청에 넣을 문장 수


class LLM:
    def __init__(self, model: str = config.ANSWER_MODEL, embed_model: str = config.EMBED_MODEL,
                 dry_run: bool = False, api_key: str | None = None,
                 reasoning_effort: str | None = config.ANSWER_EFFORT):
        self.model = model
        self.embed_model = embed_model
        self.dry_run = dry_run
        # 생각 수준(none/low/medium/…). 생각 단계가 있는 모델에만 보낸다. 생각 토큰도 출력 요금으로 청구된다.
        self.reasoning_effort = reasoning_effort if model.startswith(config.REASONING_PREFIXES) else None
        # chat 토큰 합계(비용 확인용). reasoning은 출력 토큰 가운데 생각에 쓴 몫
        self.usage = {"prompt": 0, "completion": 0, "reasoning": 0, "calls": 0}
        self._client = None
        if not dry_run:
            from openai import OpenAI

            key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()   # 공백만 있으면 키 없음(화면과 같게)
            if not key:
                raise RuntimeError("OPENAI_API_KEY가 없습니다. .env 파일에 넣거나, 키 없이 확인하려면 --dry-run 을 쓰세요.")
            # 요청이 몰려 분당 토큰 한도(429)에 걸리면 잠깐 기다렸다 다시 시도한다.
            self._client = OpenAI(api_key=key, max_retries=8)

    def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        """json_mode면 JSON 객체로만 답하게 한다(LLM 채점기용)."""
        if self.dry_run:
            return f"[DRY-RUN] 메시지 {len(messages)}개, 시스템 프롬프트 {len(messages[0]['content'])}자"
        resp = self._client.chat.completions.create(model=self.model, messages=messages, **self.params(json_mode))
        if resp.usage:
            self.usage["prompt"] += resp.usage.prompt_tokens
            self.usage["completion"] += resp.usage.completion_tokens
            details = getattr(resp.usage, "completion_tokens_details", None)
            self.usage["reasoning"] += getattr(details, "reasoning_tokens", None) or 0
        self.usage["calls"] += 1
        content = resp.choices[0].message.content
        if content is None:
            # 빈 응답(거절·길이 초과 등)이 None으로 오면 자동 점검에서 TypeError로 실행 전체가 멈췄다(코드정리검토 C1·X11).
            # 빈 답으로 기록하고 이어 간다(채점에서 오답). 이유만 알린다.
            print(f"모델이 빈 답을 돌려줌(finish_reason={resp.choices[0].finish_reason}), 빈 답으로 기록")
            return ""
        return content

    def params(self, json_mode: bool = False) -> dict:
        """모델마다 받는 설정이 다르다: 새 모델은 temperature를 거절하고, 옛 모델은 reasoning_effort를 거절한다."""
        p = {} if self.model.startswith(config.NO_TEMPERATURE_PREFIXES) else {"temperature": config.TEMPERATURE}
        if self.reasoning_effort:
            p["reasoning_effort"] = self.reasoning_effort
        if json_mode:
            p["response_format"] = {"type": "json_object"}
        return p

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.dry_run:
            raise RuntimeError("dry-run에서는 임베딩을 만들 수 없습니다. BM25 검색기를 쓰세요.")
        # 한 요청에 30만 토큰까지라서(793청크를 한 번에 보내면 넘음) 나눠서 보낸다.
        out = []
        for i in range(0, len(texts), EMBED_BATCH):
            resp = self._client.embeddings.create(model=self.embed_model, input=texts[i:i + EMBED_BATCH])
            out += [d.embedding for d in resp.data]
        return out
