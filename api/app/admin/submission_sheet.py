"""Excel workbook a recruiter downloads while submitting someone from Review."""

from app.admin.xlsx import workbook


def submission_workbook(reviews: list[dict], must_lines: list[str], nice_lines: list[str]) -> bytes:
    """Two sheets: one row per person, and one row per requirement with years filled in."""
    names = _column_names(reviews)
    people = [
        [
            index,
            review["candidate"].get("full_name") or "",
            review["candidate"].get("email") or "",
            review["candidate"].get("location") or "",
            _percent(review.get("mandatory_pct")),
            _percent(review.get("desired_pct")),
            "yes" if review.get("meets_bar") else "no",
            _met_cell(review),
        ]
        for index, review in enumerate(reviews, start=1)
    ]
    requirement_headers = ["Requirement", "Kind", *names]
    if len(reviews) == 1:
        requirement_headers.append("How the years were read")
    requirement_rows = [_requirement_row(line, "Mandatory", reviews) for line in must_lines]
    requirement_rows.extend(_requirement_row(line, "Desired", reviews) for line in nice_lines)
    return workbook(
        [
            (
                "Candidates",
                ["Rank", "Name", "Email", "Location", "Mandatory", "Desired", "Strong match", "Requirements met, with years"],
                people,
            ),
            ("Requirements", requirement_headers, requirement_rows),
        ]
    )


def excel_years(item: dict | None):
    """A number when the estimate is one length, otherwise the short label, or blank when the line is not met."""
    if item is None:
        return ""
    years = item.get("years")
    if isinstance(years, (int, float)) and item.get("basis") != "partial":
        return int(years) if float(years).is_integer() else float(years)
    return item.get("label") or "met"


def _requirement_row(line: str, kind: str, reviews: list[dict]) -> list:
    key = "mandatory_experience" if kind == "Mandatory" else "desired_experience"
    cells = [line, kind]
    details = []
    for review in reviews:
        found = next((item for item in review.get(key) or [] if item.get("line") == line), None)
        cells.append(excel_years(found))
        if found and found.get("detail"):
            details.append(found["detail"])
    if len(reviews) == 1:
        cells.append(details[0] if details else "")
    return cells


def _met_cell(review: dict) -> str:
    parts = []
    for item in list(review.get("mandatory_experience") or []) + list(review.get("desired_experience") or []):
        parts.append(f"{item.get('line')} ({item.get('label')})")
    return "; ".join(parts)


def _column_names(reviews: list[dict]) -> list[str]:
    used: dict[str, int] = {}
    names = []
    for index, review in enumerate(reviews, start=1):
        name = (review["candidate"].get("full_name") or f"Candidate {index}").strip() or f"Candidate {index}"
        count = used.get(name, 0) + 1
        used[name] = count
        names.append(name if count == 1 else f"{name} ({count})")
    return names


def _percent(value) -> str:
    if value is None:
        return ""
    return f"{round(float(value) * 100)}%"
