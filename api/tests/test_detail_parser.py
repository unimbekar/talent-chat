"""Detail parser on every careers fixture."""

from pathlib import Path

from app.core.clearance import is_clearance_only
from app.core.detail_parser import parse_detail_html
from app.core.listing_parser import parse_listing_html

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "careers"


def _visible_has(html: str, needle: str) -> bool:
    return needle.lower() in html.lower()


def test_every_detail_fixture():
    files = sorted(FIXTURES.glob("job_*.html"))
    assert len(files) == 19
    for path in files:
        html = path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_detail_html(html)
        assert parsed.description_text.strip(), path.name
        for quote in parsed.must_have_quotes + parsed.nice_to_have_quotes:
            assert not is_clearance_only(quote), (path.name, quote)
            assert not quote.lower().startswith("clearance:")
            assert not quote.lower().startswith("security clearance:")
        if "ts/sci" in html.lower() or "top secret" in html.lower():
            assert parsed.clearance_required == "ts_sci", path.name
        if "full scope" in html.lower() or "fsp" in html.lower():
            assert parsed.polygraph_required == "full_scope", path.name


def test_job_1001_listing_title_wins_over_stale_heading():
    listing = parse_listing_html(
        (FIXTURES / "career_2026-09-27.html").read_text(encoding="utf-8", errors="replace")
    )
    row = next(item for item in listing if item.requisition_code == "A1001")
    detail = parse_detail_html(
        (FIXTURES / "job_1001.html").read_text(encoding="utf-8", errors="replace")
    )
    assert row.title == "UI/UX Developer"
    assert row.location == "Chantilly, VA"
    assert "ui/ux" in detail.description_text.lower()
    assert detail.clearance_required == "ts_sci"
    assert detail.polygraph_required == "full_scope"
    assert all("clearance:" not in quote.lower() for quote in detail.must_have_quotes)


def test_job_2008_kept_whole_and_flagged():
    parsed = parse_detail_html(
        (FIXTURES / "job_2008.html").read_text(encoding="utf-8", errors="replace")
    )
    assert parsed.needs_review is True
    assert parsed.must_have_quotes == []
    assert parsed.nice_to_have_quotes == []
    assert "Full Stack Software Developer" in parsed.description_text
    assert "Mandatory Skills & Qualifications" in parsed.description_text
    assert "Backend Mastery" in parsed.description_text
    assert parsed.clearance_required == "ts_sci"
    assert parsed.polygraph_required == "full_scope"
