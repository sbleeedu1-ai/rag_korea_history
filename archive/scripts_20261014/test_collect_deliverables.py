"""collect_deliverables.py 테스트(2026-10-14 archive로 옮김, scripts/ 경로 기준이라 그대로는 돌지 않음)."""
import pytest

from scripts import collect_deliverables


def test_collect_deliverables_missing_source_keeps_existing_copies(tmp_path, monkeypatch):
    out = tmp_path / "산출물"
    (out / "1단계").mkdir(parents=True)
    (out / "README.md").write_text("기존 목록", encoding="utf-8")
    monkeypatch.setattr(collect_deliverables, "OUT", out)
    monkeypatch.setattr(collect_deliverables, "STAGES", [("1단계", "제안서", [("없는/파일.pdf", None)], [])])
    with pytest.raises(FileNotFoundError):
        collect_deliverables.main()
    assert (out / "README.md").read_text(encoding="utf-8") == "기존 목록"
    assert not (tmp_path / "산출물.new").exists()


def test_collect_deliverables_failed_final_rename_keeps_existing_copies(tmp_path, monkeypatch):
    """새 사본을 다 모은 뒤 마지막 이름 바꾸기가 실패해도 기존 사본이 남는다(코드정리검토 X2)."""
    from pathlib import Path

    out = tmp_path / "산출물"
    out.mkdir()
    (out / "README.md").write_text("기존 목록", encoding="utf-8")
    (tmp_path / "원본.md").write_text("원본", encoding="utf-8")
    monkeypatch.setattr(collect_deliverables, "ROOT", tmp_path)
    monkeypatch.setattr(collect_deliverables, "OUT", out)
    monkeypatch.setattr(collect_deliverables, "STAGES", [("1단계", "제안서", [("원본.md", None)], [])])
    original_rename = Path.rename

    def broken_rename(self, target):
        if self.name == "산출물.new":
            raise PermissionError("이름 바꾸기 실패")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", broken_rename)
    with pytest.raises(PermissionError):
        collect_deliverables.main()
    assert (out / "README.md").read_text(encoding="utf-8") == "기존 목록"
    monkeypatch.setattr(Path, "rename", original_rename)
    collect_deliverables.main()                     # 성공하면 새 사본으로 바뀌고 옆 이름 폴더는 남지 않음
    assert (out / "1단계" / "원본.md").exists() and not (tmp_path / "산출물.old").exists()
