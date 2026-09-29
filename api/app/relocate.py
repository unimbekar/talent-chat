"""Re-file each candidate's home city and state.

Run once after upgrading, and again after a large import:

    python -m app.relocate            # parser pass, then the model for rows still missing a state
    python -m app.relocate --dry-run  # print the changes without saving
    python -m app.relocate --no-llm   # parser pass only

Confirmed profiles keep the location the recruiter entered.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field

from sqlalchemy import select

from app.config import get_settings
from app.core.llm import LLMClient, LLMError, build_llm_client, parse_json_content
from app.core.structure import resume_location
from app.core.us_states import looks_like_city, state_code
from app.db import admin_session
from app.models import Candidate

HEADER_LINES = 40

LOCATION_SYSTEM = """You read the top of a résumé and report where the person lives.
Return JSON only: {"city": string or null, "state": two-letter US postal code or null, "line": string or null}.
line is the exact résumé line you read the city from, copied character for character.
Use only the contact or address lines. Ignore employers, schools, clients, and job sites.
Return nulls when the résumé does not say where the person lives.
"""


@dataclass
class Outcome:
    parser_changed: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    model_filled: list[tuple[str, str | None, str]] = field(default_factory=list)
    still_unknown: list[str] = field(default_factory=list)
    model_errors: int = 0


def _label(row: Candidate) -> str:
    return row.full_name or row.original_filename or str(row.id)


def _header(text: str | None) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return "\n".join(lines[:HEADER_LINES])[:4000]


def location_from_model(text: str | None, llm: LLMClient) -> str | None:
    """Ask the model for the home city. Keep it only if the city is in the header it was shown."""
    header = _header(text)
    if not header:
        return None
    raw = llm.complete(system=LOCATION_SYSTEM, user=header, temperature=0.0, json_mode=True)
    data = parse_json_content(raw)
    city = str(data.get("city") or "").strip()
    code = state_code(str(data.get("state") or ""))
    if not city or code is None or not looks_like_city(city):
        return None
    if city.lower() not in header.lower():
        return None
    return f"{city}, {code}"


def relocate(llm: LLMClient | None, *, dry_run: bool = False) -> Outcome:
    outcome = Outcome()
    session = admin_session()
    try:
        rows = session.scalars(select(Candidate).order_by(Candidate.full_name)).all()
        for row in rows:
            if row.status == "confirmed":
                row.location = row.location
                continue
            found = resume_location(row.redacted_text or "")
            if found != row.location:
                outcome.parser_changed.append((_label(row), row.location, found))
                row.location = found

        print(f"Parser pass done: {len(outcome.parser_changed)} changed.", flush=True)
        if llm is not None:
            pending = [row for row in rows if not row.state and row.status != "confirmed"]
            print(
                f"Asking the model about {len(pending)} candidates with no state "
                "(about 10-20 seconds each)...",
                flush=True,
            )
            for index, row in enumerate(pending, start=1):
                started = time.monotonic()
                try:
                    found = location_from_model(row.redacted_text, llm)
                except (LLMError, ValueError, TypeError):
                    outcome.model_errors += 1
                    found = None
                print(
                    f"  [{index}/{len(pending)}] {_label(row)}: {found or 'no location'} "
                    f"({time.monotonic() - started:.0f}s)",
                    flush=True,
                )
                if found:
                    outcome.model_filled.append((_label(row), row.location, found))
                    row.location = found

        outcome.still_unknown = [_label(row) for row in rows if not row.state]
        if dry_run:
            session.rollback()
        else:
            session.commit()
    finally:
        session.close()
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-file candidate home city and state.")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without saving.")
    parser.add_argument("--no-llm", action="store_true", help="Skip the model pass.")
    args = parser.parse_args()

    llm = None
    if not args.no_llm:
        settings = get_settings()
        llm = build_llm_client(
            settings.llm_backend,
            settings.llm_base_url,
            settings.llm_model,
            settings.llm_api_key,
            settings.aws_region,
        )
    outcome = relocate(llm, dry_run=args.dry_run)

    print(f"Parser changed: {len(outcome.parser_changed)}")
    for name, old, new in outcome.parser_changed:
        print(f"  {name}: {old!r} -> {new!r}")
    if llm is not None:
        print(f"Model filled: {len(outcome.model_filled)} (model errors: {outcome.model_errors})")
        for name, old, new in outcome.model_filled:
            print(f"  {name}: {old!r} -> {new!r}")
    print(f"Still no state: {len(outcome.still_unknown)}")
    for name in outcome.still_unknown:
        print(f"  {name}")
    if args.dry_run:
        print("Dry run: nothing saved.")


if __name__ == "__main__":
    main()
