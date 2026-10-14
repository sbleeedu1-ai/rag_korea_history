"""코퍼스를 만들다 실패해도 기존 완성본이 남는지(전체검토 2-8 7번)."""
import pytest

from scripts import build_corpus


def test_build_corpus_failure_keeps_existing_file(tmp_path, monkeypatch):
    out = tmp_path / "corpus.jsonl"
    out.write_text("기존 코퍼스\n", encoding="utf-8")
    monkeypatch.setattr(build_corpus, "OUT", out)
    calls = {"n": 0}
    original = build_corpus.header

    def failing_header(c):
        calls["n"] += 1
        if calls["n"] == 2:
            raise TypeError("번역 칸 형식 오류")
        return original(c)

    monkeypatch.setattr(build_corpus, "header", failing_header)
    with pytest.raises(TypeError):
        build_corpus.build()
    assert out.read_text(encoding="utf-8") == "기존 코퍼스\n"

