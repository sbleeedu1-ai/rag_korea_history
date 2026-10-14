"""무료 진단이 캐시 누락·DB 불일치 때문에 유료 호출로 넘어가지 않는지 검증한다."""
import json
import sqlite3
import sys

import pytest

from scripts import retrieval_stage_diag as diag
from sillok_rag.corpus import load_chunks, search_text
from sillok_rag.retrieval import UNKNOWN_KEY


def test_cache_only_refuses_missing_question(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"저장된 질문": [1.0, 0.0]}), encoding="utf-8")
    embedder = diag.CachedEmbedder(None, path)
    assert embedder.embed(["저장된 질문"]) == [[1.0, 0.0]]
    with pytest.raises(RuntimeError, match="유료 호출 승인"):
        embedder.embed(["저장된 질문", "없는 질문"])
    assert embedder.api_texts == 0
    assert json.loads(path.read_text(encoding="utf-8")) == {"저장된 질문": [1.0, 0.0]}


def test_default_run_stops_before_model_or_database(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["진단", "--all", "--cache", str(tmp_path / "없음.json")])

    def unexpected(*args, **kwargs):
        pytest.fail("캐시 누락을 발견한 무료 실행이 DB 검색이나 유료 모델 생성으로 넘어갔습니다.")

    from sillok_rag import llm

    monkeypatch.setattr(llm, "LLM", unexpected)
    monkeypatch.setattr(diag, "database_check", unexpected)
    with pytest.raises(SystemExit, match="API 호출 없이 중단"):
        diag.main()
    assert not (tmp_path / "없음.json").exists()


def test_paid_flag_cannot_mix_with_free_modes(monkeypatch):
    for flag in ("--preflight", "--dry-run"):
        monkeypatch.setattr(sys, "argv", ["진단", flag, "--allow-paid"])
        with pytest.raises(SystemExit) as result:
            diag.main()
        assert result.value.code == 2


def test_database_without_fingerprint_requires_full_content_match(tmp_path):
    """지문 없는 DB도 실제 내용을 전수 비교하며, 불일치를 확인하면 재구축 없이 거부한다."""
    path = tmp_path / "chroma.sqlite3"
    chunk = load_chunks()[0]
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE collections (id TEXT, name TEXT, dimension INTEGER);
            CREATE TABLE collection_metadata (collection_id TEXT, key TEXT, str_value TEXT);
            CREATE TABLE segments (id TEXT, collection TEXT);
            CREATE TABLE embeddings (id INTEGER, segment_id TEXT, embedding_id TEXT);
            CREATE TABLE embedding_metadata (id INTEGER, key TEXT, string_value TEXT, int_value INTEGER, float_value REAL);
            INSERT INTO collections VALUES ('collection', 'sillok_chunks', 3072);
            INSERT INTO collection_metadata VALUES ('collection', 'embed_model', 'text-embedding-3-large');
            INSERT INTO segments VALUES ('segment', 'collection');
        """)
        db.execute("INSERT INTO embeddings VALUES (1, 'segment', ?)", (chunk["chunk_id"],))
        db.execute("INSERT INTO embedding_metadata VALUES (1, 'chroma:document', ?, NULL, NULL)", (search_text(chunk),))
        db.execute("INSERT INTO embedding_metadata VALUES (1, 'known_key', NULL, NULL, ?)",
                   (UNKNOWN_KEY if chunk["known_key"] is None else chunk["known_key"],))
    assert diag.database_check([chunk], path)["matches"]
    changed = {**chunk, "translation": chunk["translation"] + "변경"}
    report = diag.database_check([changed], path)
    assert report["text_mismatches"] == 1 and not report["matches"]
    report = diag.database_check([{**chunk, "known_key": -1}], path)
    assert report["time_mismatches"] == 1 and not report["matches"]
    assert not diag.database_check([], path)["matches"]


def test_role_turns_carry_the_same_scene_as_real_chat():
    """역할 턴은 실제 대화처럼 장면 설정을 함께 검색한다(전체검토 2-8 5번). 사실 질문은 장면이 없다."""
    from sillok_rag.evaluate import load_scenarios

    items = {(t[0], t[1]): t for t in diag.targets(True)}
    scenarios = load_scenarios()
    for sid, qid in (("A", "A5"), ("B", "B1"), ("B", "B9"), ("C", "C1")):
        assert items[(sid, qid)][5] == scenarios[sid]["setup"]
    assert all(t[5] is None for t in items.values() if t[0] in ("holdout_v1_20260930", "holdout_v1b_20260930"))


class _Recorder:
    """임베딩 검색어를 기록만 하는 가짜(DB 없이 진단의 검색어를 확인)."""
    def __init__(self, chunks):
        self.chunks, self.texts, self.name = chunks, [], "chroma"

    def search(self, query, k, max_known=None, scene=None):
        self.texts.append(f"{scene} {query}" if scene else query)
        return [(c, 1.0) for c in self.chunks[:k]]


def test_diag_sends_scene_to_dense_search(tmp_path, monkeypatch):
    """진단의 임베딩 검색어가 실제 대화와 같다: 역할 턴은 '장면 질문', 캐시 열쇠도 같은 글."""
    chunks = load_chunks()
    rec = _Recorder(chunks)
    cache = tmp_path / "cache.json"
    items = list(diag.targets(True))
    keys = {f"{t[5]} {t[2]}" if t[5] else t[2]: [0.0] for t in items}
    cache.write_text(json.dumps(keys, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(diag, "database_check", lambda c: {"matches": True})
    monkeypatch.setattr(diag, "ChromaRetriever", lambda c, emb: rec)
    monkeypatch.setattr(sys, "argv", ["진단", "--all", "--cache", str(cache)])
    diag.main()
    role = [t for t in items if t[5]]
    assert role and all(f"{t[5]} {t[2]}" in rec.texts for t in role)
    assert not any(t in rec.texts for t in {t[2] for t in role})   # 장면 없는 검색어로는 찾지 않음

