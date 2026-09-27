"""Clearance and polygraph mapping."""

from app.core.clearance import clearance_flag, is_clearance_only, map_clearance_text, map_phrase


def test_synonym_table():
    assert map_clearance_text("Active TS/SCI with Full Scope Polygraph.") == ("ts_sci", "full_scope")
    assert map_clearance_text("Active TOP SECRET/SCI with Full Scope Polygraph") == ("ts_sci", "full_scope")
    assert map_clearance_text("TS-SCI")[0] == "ts_sci"
    assert map_clearance_text("Top Secret/SCI")[0] == "ts_sci"
    assert map_clearance_text("TOP SECRET SCI")[0] == "ts_sci"
    assert map_clearance_text("Active Top Secret") == ("ts", None)
    assert map_clearance_text("TS clearance")[0] == "ts"
    assert map_clearance_text("Secret clearance")[0] == "secret"
    assert map_clearance_text("Public Trust")[0] == "public_trust"
    assert map_clearance_text("Full-Scope Polygraph")[1] == "full_scope"
    assert map_clearance_text("FSP")[1] == "full_scope"
    assert map_clearance_text("Lifestyle Poly")[1] == "full_scope"
    assert map_clearance_text("CI Poly")[1] == "ci"
    assert map_clearance_text("Counterintelligence Polygraph")[1] == "ci"
    assert map_clearance_text("Has a Polygraph")[1] == "unknown"
    assert map_clearance_text("Poly")[1] == "unknown"
    assert map_clearance_text("") == (None, None)
    assert map_phrase("Yankee White program", "clearance") == "unknown"
    assert map_phrase(None, "clearance") is None


def test_ts_sci_does_not_also_count_as_secret_only():
    clearance, _poly = map_clearance_text("TOP SECRET")
    assert clearance == "ts"
    clearance, poly = map_clearance_text("Active TOP SECRET/SCI with Full Scope Polygraph")
    assert clearance == "ts_sci"
    assert poly == "full_scope"


def test_clearance_phrases_are_not_skills():
    assert is_clearance_only("Clearance: Active TS/SCI with Full Scope Polygraph.")
    assert is_clearance_only("TOP SECRET")
    assert not is_clearance_only("Python and AWS")


def test_clearance_flags():
    assert clearance_flag("ts_sci", "ci", "ts_sci", "full_scope") == "clearance_short"
    assert clearance_flag("unknown", "full_scope", "ts_sci", "full_scope") == "clearance_unknown"
    assert clearance_flag("ts_sci", "full_scope", "ts_sci", "full_scope") is None
    assert clearance_flag("ts", "none", "ts_sci", "full_scope") == "clearance_short"
