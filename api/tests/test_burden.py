"""Candidate burden calculator: employer taxes, benefits, 401(k), employee taxes, profit, and the submission API."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.admin.burden import (
    BurdenInputError,
    _bracket_tax,
    FEDERAL_BRACKETS,
    calculate,
    defaults,
    parse_inputs,
    summary,
)
from app.main import create_app
from app.models import AuditLog, Candidate, Job, JobApplication, Submission
from tests.fakes import RecordingEmbedder, RecordingLLM


def run(**values) -> dict:
    return calculate(parse_inputs(values))


def rows(section: dict) -> dict[str, float]:
    return {row["key"]: row["amount"] if "amount" in row else row["employer_annual"] for row in section["rows"]}


def margin_at(rate: float, result: dict, fee_pct: float = 0) -> float:
    revenue = rate * result["hours"]
    return (revenue * (1 - fee_pct / 100) - result["cost"]["annual"]) / revenue * 100


# ---------- W2 salary, every default ----------


def test_default_w2_salary_breaks_down_every_cost():
    result = run(salary=150_000, bill_rate=110)
    assert result["wages"] == 150_000
    assert result["pay_hourly"] == 72.12
    assert rows(result["employer_taxes"]) == {
        "social_security": 9_300.0,
        "medicare": 2_175.0,
        "futa": 42.0,
        "suta": 200.0,
        "workers_comp": 300.0,
    }
    assert result["employer_taxes"]["total"] == 12_017.0
    assert result["retirement"]["total"] == 15_000.0
    assert rows(result["health"]) == {"medical": 9_960.0, "dental": 540.0, "vision": 120.0}
    assert result["health"]["employee_total"] == 0
    assert rows(result["other_benefits"]) == {
        "life": 120.0,
        "std": 300.0,
        "ltd": 360.0,
        "training": 3_000.0,
        "wellness": 1_000.0,
    }
    assert result["burden"] == {"total": 42_417.0, "pct": 28.28}
    assert result["cost"]["annual"] == 192_417.0
    assert result["cost"]["hourly"] == 103.45
    assert result["unbilled_hours"] == 220
    assert result["unbilled_value"] == round(220 * 150_000 / 2080, 2)


def test_profit_margin_markup_and_status():
    billing = run(salary=150_000, bill_rate=110)["billing"]
    assert billing["revenue"] == 204_600.0
    assert billing["profit"] == 12_183.0
    assert billing["profit_hourly"] == 6.55
    assert billing["margin_pct"] == 5.95
    assert billing["markup_pct"] == 52.53
    assert billing["multiplier"] == 1.53
    assert billing["status"] == "thin"
    assert run(salary=150_000, bill_rate=90)["billing"]["status"] == "loss"
    assert run(salary=150_000, bill_rate=140)["billing"]["status"] == "profit"


def test_no_bill_rate_still_gives_break_even_and_targets():
    billing = run(salary=150_000)["billing"]
    assert billing["status"] == "unpriced"
    assert billing["profit"] is None and billing["margin_pct"] is None
    assert billing["break_even_rate"] == 103.45
    assert [step["margin_pct"] for step in billing["ladder"]] == [10, 15, 20, 25, 30]


def test_target_and_ladder_rates_hit_their_margins_with_a_fee():
    result = run(salary=150_000, bill_rate=130, fee_pct=3, target_margin_pct=22)
    billing = result["billing"]
    assert billing["fee"] == round(130 * 1860 * 0.03, 2)
    assert billing["profit"] == round(130 * 1860 * 0.97 - result["cost"]["annual"], 2)
    assert margin_at(billing["break_even_rate"], result, 3) == pytest.approx(0, abs=0.01)
    assert margin_at(billing["target_rate"], result, 3) == pytest.approx(22, abs=0.01)
    for step in billing["ladder"]:
        assert margin_at(step["rate"], result, 3) == pytest.approx(step["margin_pct"], abs=0.01)


def test_an_impossible_target_has_no_rate():
    billing = run(salary=100_000, fee_pct=40, target_margin_pct=60)["billing"]
    assert billing["target_rate"] is None
    assert billing["break_even_rate"] is not None


def test_composition_adds_up_to_the_cost():
    result = run(salary=150_000, overhead_pct=10)
    assert sum(item["amount"] for item in result["composition"]) == pytest.approx(result["cost"]["annual"], abs=0.05)
    assert sum(item["pct"] for item in result["composition"]) == pytest.approx(100, abs=0.1)
    assert result["overhead"]["amount"] == round((150_000 + 42_417) * 0.10, 2)


def test_hours_change_the_cost_per_billable_hour():
    full = run(salary=150_000, hours=2080)
    short = run(salary=150_000, hours=1600)
    assert full["cost"]["annual"] == short["cost"]["annual"]
    assert short["cost"]["hourly"] == round(full["cost"]["annual"] / 1600, 2)
    assert full["unbilled_hours"] == 0


# ---------- Limits ----------


def test_social_security_and_401k_stop_at_their_limits():
    result = run(salary=250_000)
    assert rows(result["employer_taxes"])["social_security"] == round(184_500 * 0.062, 2)
    assert rows(result["employer_taxes"])["medicare"] == round(250_000 * 0.0145, 2)
    retirement = result["retirement"]
    assert retirement["employee_deferral"] == 24_500
    assert retirement["total"] == 24_500
    assert any("24,500" in note for note in retirement["notes"])


def test_pay_above_the_compensation_limit_is_not_matched():
    retirement = run(salary=400_000, match_pct=6)["retirement"]
    assert retirement["matched_on"] == 360_000
    assert retirement["total"] == 360_000 * 0.06
    assert any("360,000" in note for note in retirement["notes"])


def test_the_match_follows_a_smaller_employee_contribution():
    retirement = run(salary=100_000, match_pct=6, employee_deferral_pct=4)["retirement"]
    assert retirement["total"] == 4_000
    assert retirement["employee_deferral"] == 4_000
    assert any("4%" in note for note in retirement["notes"])
    assert run(salary=100_000, match_pct=6, employee_deferral_pct=10)["retirement"]["total"] == 6_000


def test_the_401k_match_must_be_at_least_six_percent():
    with pytest.raises(BurdenInputError, match="at least 6%"):
        parse_inputs({"salary": 100_000, "match_pct": 5})
    assert run(salary=100_000, match_pct=6)["retirement"]["total"] == 6_000


def test_turning_off_the_401k_removes_the_match_and_the_deduction():
    result = run(salary=100_000, retirement=False)
    assert result["retirement"]["total"] == 0
    assert result["employee"]["deductions"] == []


# ---------- Health ----------


def test_family_coverage_splits_the_dependent_premium_and_lowers_taxable_pay():
    result = run(salary=120_000, tier="family")
    health = {row["key"]: row for row in result["health"]["rows"]}
    assert health["medical"]["employer_monthly"] == 830 + (2_400 - 830) / 2
    assert health["medical"]["employee_monthly"] == (2_400 - 830) / 2
    assert health["dental"]["employer_annual"] == 1_140
    assert health["vision"]["employee_annual"] == 120
    assert result["health"]["total"] == 20_760
    assert result["health"]["employee_total"] == 10_140
    # Employee premiums are pre-tax, so employer payroll taxes use the lower figure.
    taxes = rows(result["employer_taxes"])
    assert result["employer_taxes"]["taxable_wages"] == 120_000 - 10_140
    assert taxes["social_security"] == round((120_000 - 10_140) * 0.062, 2)
    assert taxes["workers_comp"] == round(120_000 * 0.002, 2)
    assert result["employee"]["deductions"][1]["amount"] == 10_140


def test_premium_overrides_and_company_share():
    result = run(salary=120_000, tier="family", medical_monthly=600, medical_dependents_monthly=1_000, dental=False, vision=False)
    medical = result["health"]["rows"][0]
    assert medical["monthly_premium"] == 1_600
    assert medical["employer_monthly"] == 1_100
    assert medical["employee_monthly"] == 500
    covered = run(salary=120_000, tier="family", dependent_share_pct=100)
    assert covered["health"]["employee_total"] == 0


def test_employee_only_coverage_ignores_dependent_premiums():
    result = run(salary=120_000, tier="employee", medical_dependents_monthly=900)
    assert result["health"]["rows"][0]["monthly_premium"] == 830


def test_benefits_can_be_switched_off():
    result = run(
        salary=120_000,
        medical=False,
        dental=False,
        vision=False,
        life_disability=False,
        training_annual=0,
        wellness_annual=0,
    )
    assert result["health"]["rows"] == [] and result["health"]["total"] == 0
    assert result["other_benefits"]["total"] == 0
    assert [item["key"] for item in result["composition"]] == ["wages", "employer_taxes", "retirement"]


def test_other_costs_add_to_the_burden():
    base = run(salary=120_000)
    extra = run(salary=120_000, other_annual=2_500)
    assert extra["burden"]["total"] - base["burden"]["total"] == 2_500


def test_state_presets_and_overrides():
    md = rows(run(salary=120_000, state="MD")["employer_taxes"])
    assert md["suta"] == round(8_500 * 0.026, 2)
    custom = run(salary=120_000, suta_rate=1.0, suta_wage_base=10_000)
    assert rows(custom["employer_taxes"])["suta"] == 100
    assert "1% of the first $10,000" in custom["employer_taxes"]["rows"][3]["note"]
    low = run(salary=5_000)
    assert rows(low["employer_taxes"])["futa"] == 30
    assert rows(low["employer_taxes"])["suta"] == 125


# ---------- Pay types ----------


def test_w2_hourly_pays_for_billable_hours():
    result = run(pay_type="w2_hourly", pay_rate=80, bill_rate=120)
    assert result["wages"] == 80 * 1860
    assert result["pay_hourly"] == 80
    assert result["unbilled_hours"] == 0
    assert result["employer_taxes"]["total"] > 0
    assert result["billing"]["multiplier"] == 1.5


def test_hourly_pay_can_come_from_a_salary():
    result = run(pay_type="w2_hourly", salary=104_000)
    assert result["pay_hourly"] == 50
    assert any("worked out from the salary" in note for note in result["notes"])


def test_1099_has_no_employer_cost_and_pays_self_employment_tax():
    result = run(pay_type="1099", pay_rate=90, bill_rate=110)
    assert result["employer_taxes"]["total"] == 0
    assert result["health"]["total"] == 0 and result["retirement"]["total"] == 0
    assert result["other_benefits"]["total"] == 0
    assert result["cost"]["hourly"] == 90
    employee = rows(result["employee"])
    earnings = 90 * 1860 * 0.9235
    assert employee["se_social_security"] == round(earnings * 0.124, 2)
    assert employee["se_medicare"] == round(earnings * 0.029, 2)
    assert result["billing"]["profit_hourly"] == 20
    assert any("no employer taxes" in note for note in result["notes"])


def test_corp_to_corp_has_no_employee_view():
    result = run(pay_type="c2c", pay_rate=100, bill_rate=115)
    assert result["employee"] is None
    assert result["billing"]["margin_pct"] == round(15 / 115 * 100, 2)


# ---------- Employee taxes ----------


def test_employee_taxes_with_2026_brackets_and_virginia():
    employee = run(salary=150_000)["employee"]
    taxes = rows(employee)
    assert taxes["social_security"] == 9_300
    assert taxes["medicare"] == 2_175
    # 150,000 - 15,000 401(k) - 16,100 standard deduction = 118,900 taxable.
    assert taxes["federal"] == 21_134
    # 150,000 - 15,000 - 8,750 - 930 = 125,320 Virginia taxable.
    assert taxes["state"] == 6_948.4
    assert employee["take_home"] == round(150_000 - 15_000 - employee["taxes_total"], 2)
    assert employee["biweekly"] == round(employee["take_home"] / 26, 2)


def test_married_flat_and_no_state_tax():
    married = rows(run(salary=150_000, filing_status="married", state_mode="none")["employee"])
    # 150,000 - 15,000 - 32,200 = 102,800: 2,480 + 9,120 + 22% of 2,000.
    assert married["federal"] == 12_040
    assert "state" not in married
    flat = rows(run(salary=150_000, federal_mode="flat", federal_rate_pct=20, state_mode="flat", state_rate_pct=4)["employee"])
    assert flat["federal"] == 27_000
    assert flat["state"] == 5_400


def test_additional_medicare_over_the_threshold():
    taxes = rows(run(salary=250_000)["employee"])
    assert taxes["additional_medicare"] == 450
    assert "additional_medicare" not in rows(run(salary=150_000)["employee"])


def test_bracket_tax_edges():
    single = FEDERAL_BRACKETS["single"]
    assert _bracket_tax(0, single) == 0
    assert _bracket_tax(12_400, single) == 1_240
    assert _bracket_tax(1_000_000, single) == pytest.approx(
        1_240 + 38_000 * 0.12 + 55_300 * 0.22 + 96_075 * 0.24 + 54_450 * 0.32 + 384_375 * 0.35 + 359_400 * 0.37
    )


# ---------- Validation and helpers ----------


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({}, "desired yearly salary"),
        ({"pay_type": "w2_hourly"}, "hourly pay"),
        ({"salary": -5}, "Desired salary must be at least 0"),
        ({"salary": 100_000, "hours": 0}, "Minimum working hours must be at least 1"),
        ({"salary": 100_000, "bill_rate": 20_000}, "Candidate hourly rate must be at most 10,000"),
        ({"salary": 100_000, "pay_type": "bogus"}, "Pay type is not one of the choices"),
        ({"salary": 100_000, "tier": "everyone"}, "not one of the choices"),
    ],
)
def test_bad_inputs_get_one_readable_sentence(values, message):
    with pytest.raises(BurdenInputError, match=message):
        parse_inputs(values)


def test_defaults_and_summary():
    data = defaults()
    assert data["tax_year"] == 2026
    assert data["inputs"]["hours"] == 1860 and data["inputs"]["match_pct"] == 10
    assert data["inputs"]["medical"] and data["inputs"]["dental"] and data["inputs"]["vision"]
    assert data["match_minimum"] == 6
    assert set(data["pay_types"]) == {"w2_salary", "w2_hourly", "1099", "c2c"}
    brief = summary(parse_inputs({"salary": 150_000, "bill_rate": 110}))
    assert brief == {"bill_rate": 110, "cost_hourly": 103.45, "profit_hourly": 6.55, "margin_pct": 5.95, "status": "thin"}


# ---------- API ----------


def _client() -> TestClient:
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.llm = RecordingLLM()
    app.state.embedder = RecordingEmbedder()
    return client


def _login(client: TestClient) -> None:
    assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200


def _seed(db) -> tuple[Job, Candidate]:
    job = Job(requisition_code="A1001", title="UI/UX Developer", location="Chantilly, VA", status="open",
              description_text="Build interfaces.", must_have_skills=["JavaScript"], nice_to_have_skills=[])
    person = Candidate(file_sha256="alex", full_name="Alex Rivera", email="alex@example.com", status="confirmed",
                       skills=[], titles=["Developer"])
    db.add_all([job, person])
    db.commit()
    return job, person


def test_burden_endpoints_need_a_sign_in(db):
    client = _client()
    assert client.post("/admin/burden", json={"salary": 100_000}).status_code == 401
    assert client.get("/admin/burden/defaults").status_code == 401


def test_calculate_endpoint_and_errors(db):
    client = _client()
    _login(client)
    defaults_body = client.get("/admin/burden/defaults").json()
    assert defaults_body["inputs"]["hours"] == 1860
    body = client.post("/admin/burden", json={"salary": 150_000, "bill_rate": 110}).json()
    assert body["result"]["cost"]["hourly"] == 103.45
    assert body["inputs"]["match_pct"] == 10
    bad = client.post("/admin/burden", json={"salary": 150_000, "match_pct": 3})
    assert bad.status_code == 400
    assert bad.json()["detail"]["message"] == "The 401(k) match must be at least 6%."


def test_a_submission_suggests_saves_and_clears_its_burden(db):
    job, person = _seed(db)
    client = _client()
    _login(client)
    created = client.post(
        "/admin/submissions", json={"candidate_id": str(person.id), "requisition_code": job.requisition_code, "salary_usd": 140_000}
    ).json()
    sid = created["id"]
    assert created["burden"]["saved"] is False
    assert created["burden"]["inputs"]["salary"] == 140_000
    assert created["burden"]["result"]["wages"] == 140_000
    assert created["burden_summary"] is None

    saved = client.put(f"/admin/submissions/{sid}/burden", json={"salary": 140_000, "bill_rate": 115, "tier": "family"})
    assert saved.status_code == 200
    burden = saved.json()
    assert burden["saved"] is True and burden["saved_at"]
    assert burden["inputs"]["tier"] == "family"
    assert burden["result"]["billing"]["bill_rate"] == 115

    detail = client.get(f"/admin/submissions/{sid}").json()
    assert detail["burden"]["saved"] is True
    card = client.get("/admin/pipeline").json()["submissions"][0]
    assert card["burden_summary"]["bill_rate"] == 115
    assert card["burden_summary"]["status"] in {"profit", "thin", "loss"}
    assert card["burden_summary"]["profit_hourly"] == burden["result"]["billing"]["profit_hourly"]

    bad = client.put(f"/admin/submissions/{sid}/burden", json={"salary": 140_000, "match_pct": 2})
    assert bad.status_code == 400
    assert client.get(f"/admin/submissions/{sid}").json()["burden"]["inputs"]["tier"] == "family"

    cleared = client.delete(f"/admin/submissions/{sid}/burden").json()
    assert cleared["saved"] is False and cleared["inputs"]["tier"] == "employee"
    assert client.get("/admin/pipeline").json()["submissions"][0]["burden_summary"] is None
    audits = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "submission_burden"))
    assert audits == 2


def test_the_applied_salary_seeds_the_calculator(db):
    job, person = _seed(db)
    row = Submission(candidate_id=person.id, job_id=job.id, stage="submitted")
    db.add(row)
    db.flush()
    db.add(JobApplication(submission_id=row.id, candidate_id=person.id, job_id=job.id, full_name="Alex Rivera",
                          email="alex@example.com", phone="555-0100", location="Chantilly, VA", salary_usd=155_000,
                          start_on=date(2026, 11, 2), years_experience=8, fsp=True))
    db.commit()
    client = _client()
    _login(client)
    burden = client.get(f"/admin/submissions/{row.id}").json()["burden"]
    assert burden["inputs"]["salary"] == 155_000
    assert burden["result"]["wages"] == 155_000


def test_no_salary_means_no_result_yet(db):
    job, person = _seed(db)
    client = _client()
    _login(client)
    created = client.post("/admin/submissions", json={"candidate_id": str(person.id), "requisition_code": job.requisition_code}).json()
    assert created["burden"]["inputs"]["salary"] is None
    assert created["burden"]["result"] is None


def test_unreadable_saved_inputs_fall_back_to_a_suggestion(db):
    job, person = _seed(db)
    row = Submission(candidate_id=person.id, job_id=job.id, stage="submitted", salary_usd=120_000,
                     burden={"inputs": {"salary": 120_000, "match_pct": 1}, "saved_at": "2026-10-12T00:00:00+00:00"})
    db.add(row)
    db.commit()
    client = _client()
    _login(client)
    assert client.get("/admin/pipeline").json()["submissions"][0]["burden_summary"] is None
    burden = client.get(f"/admin/submissions/{row.id}").json()["burden"]
    assert burden["saved"] is False and burden["inputs"]["salary"] == 120_000


def test_saving_on_a_missing_submission_is_404(db):
    client = _client()
    _login(client)
    response = client.put("/admin/submissions/00000000-0000-0000-0000-000000000000/burden", json={"salary": 1})
    assert response.status_code == 404
