"""Latest résumé per person, including mixed folders."""

from datetime import datetime, timedelta
from pathlib import Path

from app.admin.folder_ingest import filename_ignored, person_key, person_label, preferred_name, scan_resumes


def _touch(path: Path, text: str, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    stamp = when.timestamp()
    path.chmod(0o644)
    import os

    os.utime(path, (stamp, stamp))


def test_person_key_merges_folder_and_filename_spellings():
    assert person_key("Aaron Shah") == person_key("AaronShahResume2024Clearance")
    assert person_key("Evan_M_Hardy_JavaDeveloper") == person_key("Evan Hardy")
    assert person_key("Barry Ellis") == person_key("Barry-J-Ellis_IT-Leader")
    assert person_key("Non-FSP") != person_key("Joseph_Prusik")
    assert person_label("KateDribki-Resume-ETL.pdf") == "Kate Dribki"
    assert person_label("AaronShahResume2024Clearance.pdf") == "Aaron Shah"
    assert preferred_name("Big Ideas Simple Solutions", "Kate Dribki-Resume-ETL.pdf") == "Kate Dribki"
    assert preferred_name("Aaron Shah", "AaronShahResume2024Clearance.pdf") == "Aaron Shah"
    assert filename_ignored("JanusSoft_OfferLetter_Umesh.doc.pdf")
    assert filename_ignored("EmloyeeDirectDepositForm_Burton.pdf")
    assert not filename_ignored("Avery_Saunders_Resume.docx")


def test_scan_keeps_latest_named_resume_and_splits_a_pile(tmp_path: Path):
    older = datetime(2024, 1, 1)
    newer = datetime(2025, 6, 1)
    _touch(tmp_path / "ArpanSoni" / "Resume_arpan.docx", "x" * 250, older)
    _touch(tmp_path / "ArpanSoni" / "JanusSoft_Arpan_resume.pdf", "y" * 250, newer)
    _touch(tmp_path / "ArpanSoni" / "OfferLetter_ArpanSoni.pdf", "z" * 250, datetime(2026, 1, 1))
    _touch(tmp_path / "AaronShahResume2024Clearance.pdf", "a" * 250, older)
    _touch(tmp_path / "Aaron Shah" / "Aaron_Shah_resume.docx", "b" * 250, newer)
    _touch(tmp_path / "Non-FSP" / "Joseph_Prusik.pdf", "c" * 250, older)
    _touch(tmp_path / "Non-FSP" / "Suchitra Chaudhary.docx", "d" * 250, newer)
    _touch(tmp_path / "Non-FSP" / "~$seph_Prusik.docx", "e" * 250, newer)
    _touch(tmp_path / "legacy.doc", "f" * 250, newer)
    _touch(tmp_path / "JanusSoft_OfferLetter_Umesh.doc.pdf", "g" * 250, newer)

    scan = scan_resumes(tmp_path)
    chosen = {item.path.name for item in scan.chosen}
    assert "JanusSoft_Arpan_resume.pdf" in chosen
    assert "OfferLetter_ArpanSoni.pdf" not in chosen
    assert "Aaron_Shah_resume.docx" in chosen
    assert "AaronShahResume2024Clearance.pdf" not in chosen
    assert "Joseph_Prusik.pdf" in chosen
    assert "Suchitra Chaudhary.docx" in chosen
    assert "legacy.doc" not in chosen
    assert "JanusSoft_OfferLetter_Umesh.doc.pdf" not in chosen
    assert scan.older >= 2
    assert scan.ignored >= 2
