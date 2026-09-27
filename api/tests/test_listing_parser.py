"""Listing parser fixtures from SPEC.md section 3."""

from pathlib import Path

import pytest

from app.core.listing_parser import parse_listing_html, parse_listing_line

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "careers"
HREF = "https://janus-soft.com/jobs/1001"

LINES = [
    ("A1001 - UI/UX Developer - Chantilly VA", "A1001", "UI/UX Developer", "Chantilly, VA", None, None, "open"),
    ("A1002 - Senior Infrastructure Engineer - Chantilly VA", "A1002", "Senior Infrastructure Engineer", "Chantilly, VA", None, None, "open"),
    ("A1003 - Software Developer - Herndon VA", "A1003", "Software Developer", "Herndon, VA", None, None, "open"),
    ("A1004 - Mid Level Systems Engineer - UUE - Tysons VA", "A1004", "Mid Level Systems Engineer", "Tysons, VA", "UUE", None, "open"),
    ("A1005 - Platform Engineer - Herndon VA", "A1005", "Platform Engineer", "Herndon, VA", None, None, "open"),
    ("A1006 - Infrastructure Engineer - Herndon VA", "A1006", "Infrastructure Engineer", "Herndon, VA", None, None, "open"),
    ("A1007 -Palantir Data Engineer - Chantilly VA", "A1007", "Palantir Data Engineer", "Chantilly, VA", None, None, "open"),
    ("G2001 - Salesforce Developer - Mclean VA (MOON1136-08)", "G2001", "Salesforce Developer", "McLean, VA", None, "MOON1136-08", "open"),
    ("G2002 - Data Scientist - Mclean VA (STAR 2330-04)", "G2002", "Data Scientist", "McLean, VA", None, "STAR 2330-04", "open"),
    ("G2003 - AWS Cloud Engineer - Mclean VA (STAR 1435-02)", "G2003", "AWS Cloud Engineer", "McLean, VA", None, "STAR 1435-02", "open"),
    ("G2004 -Software Engineer - Mclean VA (STAR 234-01)", "G2004", "Software Engineer", "McLean, VA", None, "STAR 234-01", "open"),
    ("G2005 -Systems / Oracle Administrator - Mclean VA (STAR 2439-01)", "G2005", "Systems / Oracle Administrator", "McLean, VA", None, "STAR 2439-01", "open"),
    ("G2008 - Senior Software Developer - Mclean VA (STAR -1466-02)", "G2008", "Senior Software Developer", "McLean, VA", None, "STAR -1466-02", "open"),
    ("G2010 - Systems Engineer - Chantilly VA (STAR 1326-01)", "G2010", "Systems Engineer", "Chantilly, VA", None, "STAR 1326-01", "open"),
    ("N3001 -Data Architect - Mclean VA (23-39311)", "N3001", "Data Architect", "McLean, VA", None, "23-39311", "open"),
    ("N3010 -Multi Cloud Engineer - Chantilly VA (RV-003678-Open)", "N3010", "Multi Cloud Engineer", "Chantilly, VA", None, "RV-003678-Open", "open"),
    ("N3011 Full Stack Software / Big Data Engineer (424c)- Chantilly VA", "N3011", "Full Stack Software / Big Data Engineer", "Chantilly, VA", None, "424c", "open"),
    ("N3012 Software Quality Assurance Tester (RAP-047)- Chantilly VA", "N3012", "Software Quality Assurance Tester", "Chantilly, VA", None, "RAP-047", "open"),
    ("L4001 - Cyber Security Engineer - Herndon VA", "L4001", "Cyber Security Engineer", "Herndon, VA", None, None, "open"),
]


@pytest.mark.parametrize("line,code,title,city,program,external,status", LINES)
def test_fixture_line(line, code, title, city, program, external, status):
    row = parse_listing_line(line, href="https://janus-soft.com/jobs/1001")
    assert row is not None
    assert row.requisition_code == code
    assert row.title == title
    assert row.location == city
    assert row.program_tag == program
    assert row.external_req == external
    assert row.status == status
    assert row.source_line == line
    assert row.needs_review is False


def test_special_cases():
    palantir = parse_listing_line("A1007 -Palantir Data Engineer - Chantilly VA", href=HREF)
    assert palantir is not None
    assert palantir.title == "Palantir Data Engineer"

    no_hyphen = parse_listing_line(
        "N3011 Full Stack Software / Big Data Engineer (424c)- Chantilly VA", href=HREF
    )
    assert no_hyphen is not None
    assert no_hyphen.requisition_code == "N3011"
    assert no_hyphen.external_req == "424c"
    assert no_hyphen.location == "Chantilly, VA"

    star = parse_listing_line(
        "G2008 - Senior Software Developer - Mclean VA (STAR -1466-02)", href=HREF
    )
    assert star is not None
    assert star.external_req == "STAR -1466-02"

    proposal = parse_listing_line("Proposal - G2001 - Analyst - Ashburn VA", href=HREF)
    assert proposal is not None
    assert proposal.status == "proposal"
    assert proposal.requisition_code == "G2001"
    assert proposal.title == "Analyst"
    assert proposal.location == "Ashburn, VA"

    moon = parse_listing_line("G2099 - Engineer - Dulles VA (MOON 1150)", href=HREF)
    assert moon is not None
    assert moon.external_req == "MOON 1150"
    assert moon.location == "Dulles, VA"

    upcoming = parse_listing_line("Upcoming - A1099 - Future Role - Herndon VA", href=HREF)
    assert upcoming is not None
    assert upcoming.status == "upcoming"

    upcoming_mid = parse_listing_line("A1088 - Something upcoming - Herndon VA", href=HREF)
    assert upcoming_mid is not None
    assert upcoming_mid.status == "upcoming"


def test_separator_and_blank_ignored():
    assert parse_listing_line("-------------------------------------------------------------------------------------------------------------------") is None
    assert parse_listing_line("   ") is None


def test_no_link_flags_review_and_keeps_digits():
    row = parse_listing_line("A1001 - UI/UX Developer - Chantilly VA")
    assert row is not None
    assert row.site_job_id == "1001"
    assert row.needs_review is True


def test_ambiguous_line_is_kept():
    row = parse_listing_line("A1099 - Title without a city", href=HREF)
    assert row is not None
    assert row.requisition_code == "A1099"
    assert row.needs_review is True
    assert row.source_line == "A1099 - Title without a city"


def test_html_fixture_has_every_listing_line():
    html = (FIXTURES / "career_2026-09-27.html").read_text(encoding="utf-8", errors="replace")
    rows = parse_listing_html(html)
    codes = [row.requisition_code for row in rows]
    assert codes == [line[1] for line in LINES]
    by_code = {row.requisition_code: row for row in rows}
    assert by_code["A1007"].title == "Palantir Data Engineer"
    assert by_code["A1007"].site_job_id == "1007"
    assert by_code["N3011"].external_req == "424c"
    assert by_code["N3011"].site_job_id == "3011"
    assert by_code["G2008"].external_req == "STAR -1466-02"
    assert by_code["A1004"].program_tag == "UUE"
    assert by_code["A1001"].location == "Chantilly, VA"
    assert all(row.needs_review is False for row in rows)
