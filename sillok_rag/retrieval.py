"""검색기 두 가지.

- BM25Retriever: 글자 2-gram BM25. API 키 없이 동작하고 결과가 항상 같다.
- ChromaRetriever: 로컬 Chroma 벡터 DB 검색(OpenAI 임베딩). build-db 로 먼저 만들어야 한다.
- HybridRetriever: 위 두 검색기의 순위를 합친다(RRF). 뜻이 비슷한 청크는 임베딩이,
  같은 낱말이 나오는 청크는 BM25가 위로 끌어올린다.
- RerankRetriever: 다른 검색기로 후보를 넉넉히 뽑고, 답변 모델이 그중 k개를 고른다(새 코퍼스 2차).

역할 대화에서는 scene(인물·장면 설정 문장)을 함께 받는다. 임베딩 검색어 앞에만 붙이고 BM25는 질문 그대로 둔다
(검색기가 "상소를 올리신 까닭"만 보고 다른 상소 기사를 찾던 B1·C1·B9, 작업기록 [183]. BM25에도 붙이면 장면 낱말이
모든 턴을 같은 기사로 끌어와 C6의 다른 기사가 후보에서 빠졌다). 리랭커는 장면 한 줄을 질문과 함께 본다.

모두 max_known(장면 시점의 숫자 키, corpus.known_key)을 주면 인물이 그때 알 수 없는 청크
(known_from이 장면보다 뒤이거나 '후일 기록'인 사론·졸기 등)를 검색 전에 빼 버린다(D1 시점 필터).
Chroma는 메타데이터 조건(where)으로, BM25는 파이썬에서 거른다.
"""
import math
import re
from collections import Counter

from . import config
from .corpus import search_text

_NON_WORD = re.compile(r"[\s\W_]+", re.UNICODE)


def bigrams(text: str) -> list[str]:
    tokens = []
    for word in _NON_WORD.split(text):
        if len(word) == 1:
            tokens.append(word)
        tokens.extend(word[i:i + 2] for i in range(len(word) - 1))
    return tokens


UNKNOWN_KEY = 99999999.0  # '후일 기록' 청크의 Chroma 메타데이터 값(어떤 장면보다도 뒤)


def date_text(chunk: dict) -> str:
    """BM25 색인에만 붙이는 기록일·재위년. 예: "1466년 8월 25일 세조 12년". 날짜 없는 총서는 재위년만.

    검색 본문(search_text)에는 날짜가 없어서 "1466년 세조 때 토지 제도"처럼 연도로 묻는 질문이 정답 청크를 못 찾았다
    (F43 BM25 454위 → 1위, 작업기록 [183]). 임베딩 DB의 본문은 그대로라 DB를 다시 만들지 않는다.
    """
    date = chunk.get("record_date")
    if not date:
        return chunk.get("reign") or ""
    y, m, d = date.split("-")
    return f"{int(y)}년 {int(m)}월 {int(d)}일 {chunk.get('reign') or ''}".strip()


def gloss_text(chunk: dict) -> str:
    """청크에 붙인 쉬운 말 풀이 글을 한 줄로 잇는다(용어는 번역문에 이미 있으므로 풀이만)."""
    return " ".join(g["풀이"] for g in chunk.get("gloss") or [])


def _allowed(chunk: dict, max_known: float | None) -> bool:
    return max_known is None or (chunk["known_key"] is not None and chunk["known_key"] <= max_known)


class BM25Retriever:
    name = "bm25date"   # 2026-10-01 색인에 날짜를 넣음(date_text). 예전 결과 파일의 'bm25'와 구별

    def __init__(self, chunks: list[dict], k1: float = 1.5, b: float = 0.75, with_gloss: bool = False,
                 gloss_weight: float = config.BM25_GLOSS_WEIGHT):
        self.chunks = chunks
        self.k1, self.b = k1, b
        if with_gloss:   # 결과 파일 이름으로 풀이 색인 여부를 구별한다
            self.name = f"bm25date-gloss{gloss_weight:g}"
        # 한문 질문(번역 문항)도 찾을 수 있게 원문도 함께 색인한다.
        # 연도로 묻는 질문을 위해 기록일·재위년도 색인한다(date_text).
        # with_gloss: 쉬운 말 풀이 글도 색인한다(작업기록 [286]·[297]). 지금은 C안의 따로 도는 풀이 BM25(gloss_extra)만 켜고,
        # 하이브리드에 들어가는 기본 BM25는 풀이 없이 둔다([302]).
        self.docs = [Counter(bigrams(date_text(c) + " " + search_text(c) + " " + c["original"])) for c in chunks]
        if with_gloss:  # 풀이 글자 조각은 gloss_weight만큼만 센다(풀이에 흔한 '벼슬'·'관청'·'책'이 잡음이 되는지 보려고)
            for d, c in zip(self.docs, chunks):
                for t, v in Counter(bigrams(gloss_text(c))).items():
                    d[t] += v * gloss_weight
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = sum(self.lengths) / len(self.lengths)
        df = Counter(t for d in self.docs for t in d)
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int, max_known: float | None = None,
               scene: str | None = None) -> list[tuple[dict, float]]:
        # scene은 쓰지 않는다(장면 낱말이 모든 턴을 같은 기사로 끌어옴, 모듈 설명)
        q = Counter(bigrams(query))
        scored = []
        for chunk, doc, length in zip(self.chunks, self.docs, self.lengths):
            if not _allowed(chunk, max_known):
                continue
            score = 0.0
            for term in q:
                tf = doc.get(term, 0)
                if tf:
                    norm = tf + self.k1 * (1 - self.b + self.b * length / self.avg_len)
                    score += self.idf[term] * tf * (self.k1 + 1) / norm
            scored.append((chunk, score))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]


class ChromaRetriever:
    name = "chroma"

    def __init__(self, chunks: list[dict], embedder, collection=None):
        from .store import open_collection

        self.by_id = {c["chunk_id"]: c for c in chunks}
        self.embedder = embedder
        self.collection = collection or open_collection()

    def search(self, query: str, k: int, max_known: float | None = None,
               scene: str | None = None) -> list[tuple[dict, float]]:
        where = {"known_key": {"$lte": max_known}} if max_known is not None else None
        text = f"{scene} {query}" if scene else query
        res = self.collection.query(
            query_embeddings=self.embedder.embed([text]), n_results=k, where=where,
        )
        # cosine 거리 → 유사도
        return [(self.by_id[cid], 1 - dist) for cid, dist in zip(res["ids"][0], res["distances"][0])]


class RerankRetriever:
    """다른 검색기(base)로 후보를 n_candidates개 뽑고, 모델이 그중 k개를 골라 순서를 정한다.

    시점 필터(max_known)는 후보를 뽑을 때 base에 그대로 넘기므로, 고른 결과도 필터를 지킨다.
    모델 답이 JSON이 아니거나 API가 실패하면 base 순위를 그대로 쓴다. 모델이 k개보다 적게 고르면
    base 순위에서 나머지를 채운다.
    """

    def __init__(self, base, llm, n_candidates: int, check: bool = False):
        self.base, self.llm, self.n_candidates, self.check = base, llm, n_candidates, check
        # 리랭커 모델이 기본과 다르면 이름(결과 파일 이름)에 모델을 붙인다. 예: hybrid_rerank20-gpt-6-luna
        model = getattr(llm, "model", config.RERANK_MODEL)
        other = model if model != config.RERANK_MODEL else ""
        self.name = f"{base.name}_rerank{n_candidates}" + (f"-{other}" if other else "") + ("_check" if check else "")
        # 3차: 마지막 검색에서 '틀림'으로 판정된 전제(근거 문장이 고른 청크에 글자 그대로 있는 것만)
        self.last_premise: list[dict] = []
        # 마지막 검색의 단계 기록: 리랭커에 넘긴 후보 ID(순위대로), 모델이 실제로 고른 ID, 모델 답을 못 써서
        # 검색 순위로 대신했는지. 결과 파일에 남겨 정답이 '후보에서 빠졌나/리랭커가 버렸나'를 가린다(원인 분석 3-2)
        self.last_trace: dict | None = None

    def search(self, query: str, k: int, max_known: float | None = None,
               scene: str | None = None) -> list[tuple[dict, float]]:
        import json

        from .prompts import rerank_messages

        self.last_premise = []
        # 하이브리드는 각 검색기 상위도 꼭 넣은 후보를 준다(keep_each, 후보가 n_candidates보다 많을 수 있음)
        pool = getattr(self.base, "candidates", self.base.search)
        extra = {"scene": scene} if scene else {}
        cands = pool(query, max(self.n_candidates, k), max_known, **extra)
        self.last_trace = {"candidates": [c["chunk_id"] for c, _ in cands], "model_ids": [], "fallback": False}
        if len(cands) <= k:
            return cands
        by_id = {c["chunk_id"]: (c, s) for c, s in cands}
        premise = []
        try:
            reply = json.loads(self.llm.chat(rerank_messages(query, [c for c, _ in cands], k, self.check, scene),
                                             json_mode=True))
            ids, premise = reply["ids"], reply.get("premise") or []
        except Exception as e:  # 키가 담길 수 있어 예외 종류만 남긴다
            print(f"리랭커 실패({type(e).__name__}), 검색 순위를 그대로 씀")
            ids = []
            self.last_trace["fallback"] = True
        picked = []
        for cid in ids if isinstance(ids, list) else []:
            # 모델이 {"ids": [{}]}처럼 문자열이 아닌 것을 주면 건너뛴다(예전에는 TypeError로 멈춤, 중간 점검 보고서)
            if isinstance(cid, str) and cid in by_id and by_id[cid] not in picked:
                picked.append(by_id[cid])
        self.last_trace["model_ids"] = [c["chunk_id"] for c, _ in picked]
        for hit in cands:
            if len(picked) >= k:
                break
            if hit not in picked:
                picked.append(hit)
        picked = picked[:k]
        if self.check:
            self.last_premise = _verified_false_premises(premise, {c["chunk_id"]: c for c, _ in picked})
        return picked


def _squash(text) -> str:
    return re.sub(r"\s+", "", text if isinstance(text, str) else "")


def _verified_false_premises(premise, chosen: dict) -> list[dict]:
    """'틀림' 판정 가운데 근거 문장이 고른 청크의 번역문에 글자 그대로 있는 것만 남긴다.

    판정 모델이 근거를 지어내거나 고르지 않은 청크를 근거로 들면, 답변 모델이 그 틀린 판정을
    굳게 따라갈 수 있다(파일럿 7차 C2). 그래서 확인할 수 있는 '틀림'만 답변에 넘긴다.
    """
    kept = []
    for p in premise if isinstance(premise, list) else []:
        if not isinstance(p, dict) or p.get("verdict") != "틀림":
            continue
        cid = p.get("chunk")
        # chunk 칸에 목록·객체가 오면 사전 조회에서 TypeError로 실행 전체가 멈췄다(전체검토 2-8, 작업기록 [322])
        chunk, quote = chosen.get(cid) if isinstance(cid, str) else None, _squash(p.get("quote"))
        if chunk and len(quote) >= 5 and quote in _squash(chunk["translation"]):
            kept.append({k: str(p.get(k) or "") for k in ("claim", "chunk", "quote", "correct")})
    return kept


def tie_ranks(hits: list[tuple[dict, float]]) -> list[float]:
    """점수순으로 선 목록의 순위. 점수가 같은 묶음은 모두 그 묶음 순위의 평균(공동 순위)을 받는다.

    예전에는 동점이어도 1, 2, 3…을 차례로 붙여, BM25 0점 청크 수백 개가 코퍼스 줄 순서대로 다른 순위를 받았다.
    그 순위가 RRF 점수에 더해져 뜻 없는 파일 순서가 후보를 바꿨다(순서만 뒤집어도 진단 20문항 중 5개, 작업기록 [139]).
    0점을 빼는 안보다 평균 공동 순위가 부작용이 가장 작았다([141]).
    """
    ranks, i = [], 0
    while i < len(hits):
        j = i
        while j < len(hits) and hits[j][1] == hits[i][1]:
            j += 1
        ranks += [(i + 1 + j) / 2] * (j - i)
        i = j
    return ranks


class HybridRetriever:
    """임베딩 순위와 BM25 순위를 RRF(Reciprocal Rank Fusion)로 합친다.

    청크마다 점수 = 1/(rrf_k + 임베딩 순위) + 1/(rrf_k + BM25 순위).
    두 검색기의 점수 단위가 달라서(코사인 유사도 vs BM25 점수) 점수 대신 순위만 쓴다. 동점은 공동 순위(tie_ranks).
    rrf_k=60은 RRF 논문에서 흔히 쓰는 기본값이다.

    keep_each: 리랭커에 넘길 후보(candidates)에 합친 순위 상위 k개와 함께 **임베딩 상위 keep_each개, BM25 상위 keep_each개
    (0점 제외)**를 꼭 넣는다. 한쪽 검색기만 위로 찾은 정답이 다른 쪽 순위에 끌려 20위 밖으로 밀리던 문제
    (F05·HP01 등, 작업기록 [135]) 때문. 20칸 안에서 자리를 나누면 양쪽 모두 중간인 정답이 밀려서(B1) 후보 수를 늘리는 쪽을 택함([143]).
    """

    def __init__(self, dense, sparse, rrf_k: int = 60, keep_each: int = 0, extra: list | None = None):
        self.dense, self.sparse, self.rrf_k, self.keep_each = dense, sparse, rrf_k, keep_each
        # extra: [(검색기, 개수)]. 합치기(RRF)에는 끼지 않고 상위 몇 개만 리랭커 후보에 보탠다(C안, 풀이 BM25, 작업기록 [302])
        self.extra = extra or []
        self.n = len(sparse.chunks)
        # 결과 파일 이름에 남는다. 동점 처리를 바꾼 뒤(2026-10-01)의 결과를 예전 'hybrid'와 구별한다
        # 2026-10-01 BM25 색인에 날짜를 넣은 뒤는 '-date'(sparse.name이 bm25date일 때)
        # BM25에 풀이 글을 섞으면(B안, 진단 --bm25-gloss) '-gloss<가중치>'(sparse.name이 bm25date-gloss…일 때)
        sname = getattr(sparse, "name", "")
        date = "-date" if sname.startswith("bm25date") else ""
        gloss = sname[len("bm25date"):] if sname.startswith("bm25date-gloss") else ""
        self.name = ("hybrid-avgtie" + (f"-keep{keep_each}" if keep_each else "") + date + gloss
                     + "".join(f"-glosskeep{n}" for _, n in self.extra))

    def _merged(self, query: str, max_known: float | None, scene: str | None = None):
        # 두 검색기 모두 (시점 필터를 통과한) 청크 전체를 줄 세운 뒤 합친다.
        scores: dict[str, float] = {}
        by_id: dict[str, dict] = {}
        tops = []
        for retriever in (self.dense, self.sparse):
            # 장면 문장은 임베딩 쪽에만 넘긴다(모듈 설명)
            extra = {"scene": scene} if scene and retriever is self.dense else {}
            hits = retriever.search(query, self.n, max_known, **extra)
            for rank, (chunk, _) in zip(tie_ranks(hits), hits):
                cid = chunk["chunk_id"]
                by_id[cid] = chunk
                scores[cid] = scores.get(cid, 0.0) + 1 / (self.rrf_k + rank)
            tops.append([c["chunk_id"] for c, s in hits[:self.keep_each] if retriever is self.dense or s > 0])
        ranked = sorted(scores, key=lambda cid: -scores[cid])
        return ranked, scores, by_id, tops

    def search(self, query: str, k: int, max_known: float | None = None,
               scene: str | None = None) -> list[tuple[dict, float]]:
        ranked, scores, by_id, _ = self._merged(query, max_known, scene)
        return [(by_id[cid], scores[cid]) for cid in ranked[:k]]

    def candidates(self, query: str, k: int, max_known: float | None = None,
                   scene: str | None = None) -> list[tuple[dict, float]]:
        """리랭커용 후보: 합친 순위 상위 k개 + 각 검색기 상위 keep_each개. 합친 점수 순서로, k개보다 많을 수 있다."""
        ranked, scores, by_id, tops = self._merged(query, max_known, scene)
        for retriever, n in self.extra:   # 시점 필터는 같게, 0점은 빼고
            tops.append([c["chunk_id"] for c, s in retriever.search(query, n, max_known) if s > 0])
        keep = set(ranked[:k]).union(*tops)
        return [(by_id[cid], scores[cid]) for cid in ranked if cid in keep]


def gloss_extra(chunks: list[dict]) -> list:
    """C안: 풀이 글을 섞은 BM25를 따로 두어 상위 config.GLOSS_KEEP개를 후보에 보탠다(0이면 없음)."""
    if not config.GLOSS_KEEP:
        return []
    return [(BM25Retriever(chunks, with_gloss=True, gloss_weight=config.BM25_GLOSS_WEIGHT), config.GLOSS_KEEP)]
