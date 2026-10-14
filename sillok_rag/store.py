"""Chroma 벡터 DB(로컬 폴더 저장) 만들기.

- 원본 데이터는 data/corpus.jsonl 이고, Chroma는 거기서 다시 만들 수 있는 검색용 저장소다.
- 청크마다 기사 ID·화자·알려진 시점(known_from과 그 숫자 키 known_key)을 메타데이터로 넣어 D 조건 시점 필터에 쓴다.
  Chroma의 크기 비교 조건은 숫자에만 되므로 숫자 키를 넣는다.
- 임베딩은 OpenAI 임베딩 모델로 직접 만들어 넣는다(Chroma 기본 임베딩은 한국어에 약함).
- 정답표(data/eval)는 넣지 않는다.
"""
from pathlib import Path

from . import config
from .corpus import corpus_fingerprint, load_chunks, search_text
from .retrieval import UNKNOWN_KEY

COLLECTION = "sillok_chunks"


def _client(persist_dir: Path):
    import chromadb

    return chromadb.PersistentClient(path=str(persist_dir))


def build_chroma(embedder, persist_dir: Path = config.CHROMA_DIR, chunks: list[dict] | None = None) -> int:
    """컬렉션을 새로 만든다. embedder는 .embed(texts)와 .embed_model 을 가진 객체.

    새 DB를 임시 이름의 컬렉션에 끝까지 만든 뒤에야 기존 컬렉션을 지우고 이름을 바꾼다.
    예전에는 기존 DB부터 지워서, 임베딩(유료)이나 저장이 중간에 실패하면 검색 자료가 모두 사라졌다(전체검토 2-8 1번).
    """
    chunks = chunks or load_chunks()
    docs = [search_text(c) for c in chunks]
    vectors = embedder.embed(docs)   # 여기서 실패하면 DB는 손대지 않은 그대로
    if len(vectors) != len(docs):
        raise RuntimeError(f"임베딩 수({len(vectors)})가 청크 수({len(docs)})와 다릅니다. 기존 DB는 그대로 둡니다.")
    client = _client(persist_dir)
    tmp, old = COLLECTION + "_new", COLLECTION + "_old"
    names = [c.name for c in client.list_collections()]
    if tmp in names:   # 지난번 실패로 남은 임시 컬렉션
        client.delete_collection(tmp)
    if old in names:   # 지난번 교체가 중간에 멈춤: 정상 이름이 없으면 옛 DB를 되살리고, 있으면 남은 옛 DB를 지운다
        if COLLECTION in names:
            client.delete_collection(old)
        else:
            client.get_collection(old).modify(name=COLLECTION)
    col = client.create_collection(
        tmp, embedding_function=None,
        metadata={"hnsw:space": "cosine", "embed_model": embedder.embed_model,
                  "corpus_fp": corpus_fingerprint(chunks)},
    )
    try:
        col.add(
            ids=[c["chunk_id"] for c in chunks],
            documents=docs,
            embeddings=vectors,
            metadatas=[{
                "article_id": c["article_id"],
                "record_date": c["record_date"] or "",   # 태조실록 총서는 날짜가 없다(Chroma는 빈 값을 못 받음)
                "known_from": c["known_from"] or "",
                "known_key": UNKNOWN_KEY if c["known_key"] is None else c["known_key"],
                "speaker": c["speaker"],
            } for c in chunks],
        )
        if col.count() != len(chunks):
            raise RuntimeError(f"새 DB에 {col.count()}개만 저장됨(청크 {len(chunks)}개). 기존 DB는 그대로 둡니다.")
    except Exception:
        client.delete_collection(tmp)
        raise
    # 기존 DB를 먼저 지우면 이름 바꾸기가 실패할 때 DB가 사라졌다(코드정리검토 X1·C21).
    # 기존 DB를 옆 이름으로 비켜 두고, 새 DB 이름을 바꾼 뒤에야 지운다. 실패하면 기존 DB를 원래 이름으로 돌린다.
    had_old = COLLECTION in [c.name for c in client.list_collections()]
    if had_old:
        client.get_collection(COLLECTION).modify(name=old)
    try:
        col.modify(name=COLLECTION)
    except Exception:
        if had_old:
            client.get_collection(old).modify(name=COLLECTION)
        raise
    if had_old:
        client.delete_collection(old)
    return len(chunks)


def chroma_ready(persist_dir: Path = config.CHROMA_DIR) -> bool:
    if not Path(persist_dir).exists():
        return False
    try:
        return _client(persist_dir).get_collection(COLLECTION).count() > 0
    except Exception:
        return False


def chroma_matches(chunks: list[dict], persist_dir: Path = config.CHROMA_DIR) -> bool:
    """DB가 지금 코퍼스로, 지금 임베딩 모델로 끝까지 만든 것인가.

    build-db 때 저장한 지문에 더해 임베딩 모델 이름과 청크 수도 본다. 지문만 보면 다른 모델로 만든 DB나
    일부만 들어간 DB도 맞다고 보고, 유료 질문 임베딩을 만든 뒤에야 검색이 실패했다(전체검토 2-8 6번).
    지문이 없는 옛 DB도 다르다고 본다.
    """
    try:
        col = _client(persist_dir).get_collection(COLLECTION)
        meta, count = col.metadata or {}, col.count()
    except Exception:
        return False
    return (meta.get("corpus_fp") == corpus_fingerprint(chunks)
            and meta.get("embed_model") == config.EMBED_MODEL and count == len(chunks))


def open_collection(persist_dir: Path = config.CHROMA_DIR):
    return _client(persist_dir).get_collection(COLLECTION, embedding_function=None)
