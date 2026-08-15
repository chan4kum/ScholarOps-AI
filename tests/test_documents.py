from pathlib import Path

from opportunity_intel.documents.extract import extract_text, truncate


def test_extract_txt(tmp_path: Path) -> None:
    path = tmp_path / "cv.txt"
    path.write_text("MSc Data Science\nAgentic AI research", encoding="utf-8")
    assert "Agentic AI" in extract_text(path)


def test_truncate() -> None:
    assert truncate("abc", 10) == "abc"
    assert truncate("x" * 20, 10).endswith("[truncated]")
