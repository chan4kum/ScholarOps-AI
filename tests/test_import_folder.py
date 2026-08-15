from pathlib import Path

from opportunity_intel.documents.import_folder import guess_doc_type, iter_importable_files


def test_guess_doc_type() -> None:
    assert guess_doc_type("Chandan_Kumar_Academic_CV.pdf") == "academic_cv"
    assert guess_doc_type("Cover_Letter_BTH.pdf") == "cover_letter"
    assert guess_doc_type("Statementofbackground.pdf") == "research_proposal"
    assert guess_doc_type("CV_Chandan_Kumar_WASP_Linkoping.md") == "academic_cv"


def test_iter_importable_files_skips_agents(tmp_path: Path) -> None:
    root = tmp_path / "PHD"
    root.mkdir()
    (root / "cv.pdf").write_bytes(b"%PDF")
    agents = root / ".agents" / "skills"
    agents.mkdir(parents=True)
    (agents / "SKILL.md").write_text("skill", encoding="utf-8")
    (root / "Applications").mkdir()
    (root / "Applications" / "Cover_Letter.md").write_text("letter", encoding="utf-8")

    files = iter_importable_files(root)
    names = {p.name for p in files}
    assert "cv.pdf" in names
    assert "Cover_Letter.md" in names
    assert "SKILL.md" not in names
