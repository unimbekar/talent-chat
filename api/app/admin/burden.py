"""Candidate burden: what a hire costs per year and per billable hour, and the profit at a bill rate.

Federal figures are the 2026 values. State unemployment, workers' compensation, and premium
defaults are starting points; every one can be changed in the calculator.
"""

from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

TAX_YEAR = 2026

SS_RATE = 6.2
SS_WAGE_BASE = 184_500
MEDICARE_RATE = 1.45
ADDITIONAL_MEDICARE_RATE = 0.9
ADDITIONAL_MEDICARE_THRESHOLD = {"single": 200_000, "married": 250_000}
FUTA_RATE = 0.6
FUTA_WAGE_BASE = 7_000
SE_EARNINGS_SHARE = 0.9235

DEFERRAL_LIMIT = 24_500
COMP_LIMIT = 360_000
MATCH_MINIMUM = 6

STANDARD_DEDUCTION = {"single": 16_100, "married": 32_200}
FEDERAL_BRACKETS = {
    "single": [(12_400, 10), (50_400, 12), (105_700, 22), (201_775, 24), (256_225, 32), (640_600, 35), (None, 37)],
    "married": [(24_800, 10), (100_800, 12), (211_400, 22), (403_550, 24), (512_450, 32), (768_700, 35), (None, 37)],
}
VA_BRACKETS = [(3_000, 2), (5_000, 3), (17_000, 5), (None, 5.75)]
VA_DEDUCTION = {"single": 8_750 + 930, "married": 17_500 + 1_860}

STATES = {
    "VA": {"label": "Virginia", "suta_rate": 2.5, "suta_wage_base": 8_000},
    "MD": {"label": "Maryland", "suta_rate": 2.6, "suta_wage_base": 8_500},
    "DC": {"label": "District of Columbia", "suta_rate": 2.7, "suta_wage_base": 9_000},
    "other": {"label": "Other state", "suta_rate": 2.7, "suta_wage_base": 9_000},
}

TIERS = {
    "employee": "Employee only",
    "employee_spouse": "Employee + spouse",
    "employee_children": "Employee + children",
    "family": "Family",
}
PLANS = {"medical": "Medical", "dental": "Dental", "vision": "Vision"}
# Monthly total premium by coverage tier.
PREMIUMS = {
    "medical": {"employee": 830, "employee_spouse": 1_750, "employee_children": 1_550, "family": 2_400},
    "dental": {"employee": 45, "employee_spouse": 90, "employee_children": 100, "family": 145},
    "vision": {"employee": 10, "employee_spouse": 20, "employee_children": 20, "family": 30},
}

PAY_TYPES = {
    "w2_salary": "W2 salary",
    "w2_hourly": "W2 hourly",
    "1099": "1099 hourly",
    "c2c": "Corp-to-corp hourly",
}
LADDER = (10, 15, 20, 25, 30)
THIN_MARGIN = 10

LABELS = {
    "pay_type": "Pay type",
    "salary": "Desired salary",
    "pay_rate": "Hourly pay",
    "hours": "Minimum working hours",
    "paid_hours": "Paid hours",
    "match_pct": "401(k) match",
    "employee_deferral_pct": "Employee 401(k) contribution",
    "dependent_share_pct": "Company share for dependents",
    "suta_rate": "State unemployment rate",
    "suta_wage_base": "State unemployment wage base",
    "workers_comp_pct": "Workers' compensation",
    "futa_rate": "Federal unemployment rate",
    "bill_rate": "Candidate hourly rate",
    "fee_pct": "Client or MSP fee",
    "overhead_pct": "Overhead and G&A",
    "target_margin_pct": "Target margin",
    "federal_rate_pct": "Federal income tax rate",
    "state_rate_pct": "State income tax rate",
}


class BurdenInputError(ValueError):
    pass


class BurdenIn(BaseModel):
    pay_type: Literal["w2_salary", "w2_hourly", "1099", "c2c"] = "w2_salary"
    salary: float | None = Field(default=None, ge=0, le=5_000_000)
    pay_rate: float | None = Field(default=None, ge=0, le=5_000)
    hours: float = Field(default=1860, ge=1, le=4_000)
    paid_hours: float = Field(default=2080, ge=1, le=4_000)

    medical: bool = True
    dental: bool = True
    vision: bool = True
    tier: Literal["employee", "employee_spouse", "employee_children", "family"] = "employee"
    dependent_share_pct: float = Field(default=50, ge=0, le=100)
    medical_monthly: float | None = Field(default=None, ge=0, le=20_000)
    dental_monthly: float | None = Field(default=None, ge=0, le=5_000)
    vision_monthly: float | None = Field(default=None, ge=0, le=5_000)
    medical_dependents_monthly: float | None = Field(default=None, ge=0, le=20_000)
    dental_dependents_monthly: float | None = Field(default=None, ge=0, le=5_000)
    vision_dependents_monthly: float | None = Field(default=None, ge=0, le=5_000)

    life_disability: bool = True
    life_monthly: float = Field(default=10, ge=0, le=5_000)
    std_monthly: float = Field(default=25, ge=0, le=5_000)
    ltd_monthly: float = Field(default=30, ge=0, le=5_000)
    training_annual: float = Field(default=3_000, ge=0, le=100_000)
    wellness_annual: float = Field(default=1_000, ge=0, le=100_000)
    other_annual: float = Field(default=0, ge=0, le=1_000_000)

    retirement: bool = True
    match_pct: float = Field(default=10, ge=MATCH_MINIMUM, le=100)
    employee_deferral_pct: float | None = Field(default=None, ge=0, le=100)

    state: Literal["VA", "MD", "DC", "other"] = "VA"
    suta_rate: float | None = Field(default=None, ge=0, le=20)
    suta_wage_base: float | None = Field(default=None, ge=0, le=500_000)
    futa_rate: float = Field(default=FUTA_RATE, ge=0, le=6)
    workers_comp_pct: float = Field(default=0.2, ge=0, le=20)

    filing_status: Literal["single", "married"] = "single"
    federal_mode: Literal["estimate", "flat"] = "estimate"
    federal_rate_pct: float = Field(default=15, ge=0, le=60)
    state_mode: Literal["va", "flat", "none"] = "va"
    state_rate_pct: float = Field(default=5, ge=0, le=20)

    bill_rate: float | None = Field(default=None, ge=0, le=10_000)
    fee_pct: float = Field(default=0, ge=0, le=50)
    overhead_pct: float = Field(default=0, ge=0, le=200)
    target_margin_pct: float = Field(default=20, ge=0, le=90)

    @model_validator(mode="after")
    def _pay_is_given(self):
        if self.pay_type == "w2_salary" and not self.salary:
            raise ValueError("Enter the desired yearly salary.")
        if self.pay_type != "w2_salary" and not self.pay_rate and not self.salary:
            raise ValueError("Enter the hourly pay.")
        return self


def parse_inputs(data: dict) -> BurdenIn:
    """Validated inputs, or a BurdenInputError with one readable sentence."""
    try:
        return BurdenIn.model_validate(data or {})
    except ValidationError as error:
        first = error.errors()[0]
        field = first["loc"][0] if first.get("loc") else ""
        label = LABELS.get(str(field), str(field).replace("_", " ").capitalize())
        message = first["msg"].removeprefix("Value error, ")
        if first["type"] == "greater_than_equal" and field == "match_pct":
            message = f"The 401(k) match must be at least {MATCH_MINIMUM}%."
            raise BurdenInputError(message) from None
        if first["type"] == "literal_error":
            raise BurdenInputError(f"{label} is not one of the choices.") from None
        if first["type"] in {"greater_than_equal", "less_than_equal"}:
            limit = first.get("ctx", {}).get("ge", first.get("ctx", {}).get("le"))
            word = "at least" if first["type"] == "greater_than_equal" else "at most"
            message = f"{label} must be {word} {limit:,g}." if isinstance(limit, (int, float)) else f"{label}: {message}"
            raise BurdenInputError(message) from None
        raise BurdenInputError(message if not field else f"{label}: {message}") from None


def defaults() -> dict:
    return {
        "tax_year": TAX_YEAR,
        "inputs": BurdenIn.model_construct().model_dump() | {"salary": None},
        "pay_types": PAY_TYPES,
        "tiers": TIERS,
        "plans": PLANS,
        "premiums": PREMIUMS,
        "states": STATES,
        "match_minimum": MATCH_MINIMUM,
        "limits": {
            "ss_wage_base": SS_WAGE_BASE,
            "futa_wage_base": FUTA_WAGE_BASE,
            "deferral_limit": DEFERRAL_LIMIT,
            "comp_limit": COMP_LIMIT,
        },
    }


def _r(value: float) -> float:
    return round(value + 0.0, 2)


def _bracket_tax(taxable: float, brackets: list[tuple[float | None, float]]) -> float:
    tax = 0.0
    floor = 0.0
    for ceiling, rate in brackets:
        if taxable <= floor:
            break
        top = taxable if ceiling is None else min(taxable, ceiling)
        tax += (top - floor) * rate / 100
        if ceiling is None:
            break
        floor = ceiling
    return tax


def _wages(inputs: BurdenIn) -> tuple[float, float]:
    """Yearly pay, and the hourly pay it works out to."""
    if inputs.pay_type == "w2_salary":
        wages = float(inputs.salary or 0)
        return wages, wages / inputs.paid_hours
    rate = inputs.pay_rate if inputs.pay_rate else (inputs.salary or 0) / inputs.paid_hours
    return rate * inputs.hours, rate


def _health(inputs: BurdenIn, w2: bool) -> dict:
    rows = []
    share = inputs.dependent_share_pct / 100
    for plan, label in PLANS.items():
        if not w2 or not getattr(inputs, plan):
            continue
        table = PREMIUMS[plan]
        base = getattr(inputs, f"{plan}_monthly")
        base = table["employee"] if base is None else base
        extra = getattr(inputs, f"{plan}_dependents_monthly")
        if extra is None:
            extra = table[inputs.tier] - table["employee"]
        if inputs.tier == "employee":
            extra = 0.0
        employer = base + extra * share
        employee = extra * (1 - share)
        rows.append(
            {
                "key": plan,
                "label": label,
                "monthly_premium": _r(base + extra),
                "employer_monthly": _r(employer),
                "employee_monthly": _r(employee),
                "employer_annual": _r(employer * 12),
                "employee_annual": _r(employee * 12),
            }
        )
    return {
        "tier": inputs.tier,
        "tier_label": TIERS[inputs.tier],
        "rows": rows,
        "total": _r(sum(row["employer_annual"] for row in rows)),
        "employee_total": _r(sum(row["employee_annual"] for row in rows)),
    }


def _retirement(inputs: BurdenIn, wages: float, w2: bool) -> dict:
    if not w2 or not inputs.retirement:
        return {"enabled": False, "total": 0.0, "match_pct": inputs.match_pct, "employee_deferral": 0.0}
    deferral_pct = inputs.match_pct if inputs.employee_deferral_pct is None else inputs.employee_deferral_pct
    eligible = min(wages, COMP_LIMIT)
    deferral = min(eligible * deferral_pct / 100, DEFERRAL_LIMIT)
    match = min(eligible * inputs.match_pct / 100, deferral)
    notes = []
    if deferral_pct < inputs.match_pct:
        notes.append(f"The employee puts in {deferral_pct:g}%, so the match is {deferral_pct:g}% too.")
    if eligible * deferral_pct / 100 > DEFERRAL_LIMIT:
        notes.append(f"Employee contributions stop at the {TAX_YEAR} limit of ${DEFERRAL_LIMIT:,}, so the match stops there too.")
    if wages > COMP_LIMIT:
        notes.append(f"Pay above ${COMP_LIMIT:,} is not counted for the match.")
    return {
        "enabled": True,
        "match_pct": inputs.match_pct,
        "employee_deferral_pct": deferral_pct,
        "employee_deferral": _r(deferral),
        "matched_on": _r(eligible),
        "total": _r(match),
        "effective_pct": _r(match / wages * 100) if wages else 0.0,
        "notes": notes,
    }


def _employer_taxes(inputs: BurdenIn, wages: float, pre_tax_health: float, w2: bool) -> dict:
    if not w2:
        return {"rows": [], "total": 0.0, "taxable_wages": 0.0}
    taxable = max(wages - pre_tax_health, 0.0)
    state = STATES[inputs.state]
    suta_rate = state["suta_rate"] if inputs.suta_rate is None else inputs.suta_rate
    suta_base = state["suta_wage_base"] if inputs.suta_wage_base is None else inputs.suta_wage_base
    lines = [
        ("social_security", "Social Security", SS_RATE, min(taxable, SS_WAGE_BASE), f"{SS_RATE}% up to ${SS_WAGE_BASE:,}"),
        ("medicare", "Medicare", MEDICARE_RATE, taxable, f"{MEDICARE_RATE}% with no cap"),
        ("futa", "Federal unemployment (FUTA)", inputs.futa_rate, min(taxable, FUTA_WAGE_BASE), f"{inputs.futa_rate:g}% of the first ${FUTA_WAGE_BASE:,}"),
        ("suta", f"State unemployment ({inputs.state if inputs.state != 'other' else 'SUTA'})", suta_rate, min(taxable, suta_base), f"{suta_rate:g}% of the first ${suta_base:,.0f}"),
        ("workers_comp", "Workers' compensation", inputs.workers_comp_pct, wages, f"{inputs.workers_comp_pct:g}% of pay"),
    ]
    rows = [
        {"key": key, "label": label, "rate": rate, "base": _r(base), "amount": _r(base * rate / 100), "note": note}
        for key, label, rate, base, note in lines
    ]
    return {"rows": rows, "total": _r(sum(row["amount"] for row in rows)), "taxable_wages": _r(taxable)}


def _other_benefits(inputs: BurdenIn, w2: bool) -> dict:
    if not w2:
        return {"rows": [], "total": 0.0}
    lines = []
    if inputs.life_disability:
        lines += [
            ("life", "Life insurance", inputs.life_monthly * 12),
            ("std", "Short-term disability", inputs.std_monthly * 12),
            ("ltd", "Long-term disability", inputs.ltd_monthly * 12),
        ]
    lines += [
        ("training", "Training and tuition", inputs.training_annual),
        ("wellness", "Health and technology allowance", inputs.wellness_annual),
        ("other", "Other (equipment, clearance, onboarding)", inputs.other_annual),
    ]
    rows = [{"key": key, "label": label, "amount": _r(amount)} for key, label, amount in lines if amount]
    return {"rows": rows, "total": _r(sum(row["amount"] for row in rows))}


def _employee(inputs: BurdenIn, wages: float, deferral: float, health_share: float) -> dict | None:
    if inputs.pay_type == "c2c":
        return None
    status = inputs.filing_status
    rows = []
    if inputs.pay_type == "1099":
        earnings = wages * SE_EARNINGS_SHARE
        social = min(earnings, SS_WAGE_BASE) * SS_RATE * 2 / 100
        medicare = earnings * MEDICARE_RATE * 2 / 100
        extra = max(earnings - ADDITIONAL_MEDICARE_THRESHOLD[status], 0) * ADDITIONAL_MEDICARE_RATE / 100
        rows.append({"key": "se_social_security", "label": "Self-employment Social Security", "amount": _r(social)})
        rows.append({"key": "se_medicare", "label": "Self-employment Medicare", "amount": _r(medicare + extra)})
        income_base = wages - (social + medicare) / 2
        pre_tax = 0.0
    else:
        fica_wages = max(wages - health_share, 0)
        social = min(fica_wages, SS_WAGE_BASE) * SS_RATE / 100
        medicare = fica_wages * MEDICARE_RATE / 100
        extra = max(fica_wages - ADDITIONAL_MEDICARE_THRESHOLD[status], 0) * ADDITIONAL_MEDICARE_RATE / 100
        rows.append({"key": "social_security", "label": "Social Security", "amount": _r(social)})
        rows.append({"key": "medicare", "label": "Medicare", "amount": _r(medicare)})
        if extra:
            rows.append({"key": "additional_medicare", "label": "Additional Medicare", "amount": _r(extra)})
        pre_tax = deferral + health_share
        income_base = wages - pre_tax
    if inputs.federal_mode == "flat":
        federal = max(income_base, 0) * inputs.federal_rate_pct / 100
    else:
        federal = _bracket_tax(max(income_base - STANDARD_DEDUCTION[status], 0), FEDERAL_BRACKETS[status])
    rows.append({"key": "federal", "label": "Federal income tax", "amount": _r(federal)})
    if inputs.state_mode == "va":
        state = _bracket_tax(max(income_base - VA_DEDUCTION[status], 0), VA_BRACKETS)
        rows.append({"key": "state", "label": "Virginia income tax", "amount": _r(state)})
    elif inputs.state_mode == "flat":
        state = max(income_base, 0) * inputs.state_rate_pct / 100
        rows.append({"key": "state", "label": "State income tax", "amount": _r(state)})
    taxes = sum(row["amount"] for row in rows)
    take_home = wages - taxes - (pre_tax if inputs.pay_type != "1099" else 0)
    return {
        "gross": _r(wages),
        "rows": rows,
        "taxes_total": _r(taxes),
        "effective_rate_pct": _r(taxes / wages * 100) if wages else 0.0,
        "deductions": [
            row
            for row in (
                {"key": "deferral", "label": "401(k) contribution", "amount": _r(deferral)},
                {"key": "health", "label": "Health premiums (dependents)", "amount": _r(health_share)},
            )
            if row["amount"] and inputs.pay_type != "1099"
        ],
        "take_home": _r(take_home),
        "monthly": _r(take_home / 12),
        "biweekly": _r(take_home / 26),
    }


def _rate_for(cost: float, hours: float, fee_pct: float, margin_pct: float) -> float | None:
    room = 1 - fee_pct / 100 - margin_pct / 100
    if room <= 0 or hours <= 0:
        return None
    return _r(cost / (hours * room))


def _billing(inputs: BurdenIn, cost: float, pay_hourly: float) -> dict:
    hours = inputs.hours
    payload = {
        "bill_rate": inputs.bill_rate,
        "fee_pct": inputs.fee_pct,
        "break_even_rate": _rate_for(cost, hours, inputs.fee_pct, 0),
        "target_margin_pct": inputs.target_margin_pct,
        "target_rate": _rate_for(cost, hours, inputs.fee_pct, inputs.target_margin_pct),
        "ladder": [{"margin_pct": margin, "rate": _rate_for(cost, hours, inputs.fee_pct, margin)} for margin in LADDER],
        "revenue": None,
        "profit": None,
        "profit_hourly": None,
        "margin_pct": None,
        "markup_pct": None,
        "multiplier": None,
        "status": "unpriced",
    }
    if not inputs.bill_rate:
        return payload
    revenue = inputs.bill_rate * hours
    fee = revenue * inputs.fee_pct / 100
    profit = revenue - fee - cost
    margin = profit / revenue * 100
    payload.update(
        {
            "revenue": _r(revenue),
            "fee": _r(fee),
            "net_revenue": _r(revenue - fee),
            "profit": _r(profit),
            "profit_hourly": _r(profit / hours),
            "margin_pct": _r(margin),
            "markup_pct": _r((inputs.bill_rate / pay_hourly - 1) * 100) if pay_hourly else None,
            "multiplier": _r(inputs.bill_rate / pay_hourly) if pay_hourly else None,
            "status": "loss" if profit < 0 else "thin" if margin < THIN_MARGIN else "profit",
        }
    )
    return payload


def calculate(inputs: BurdenIn) -> dict:
    w2 = inputs.pay_type in {"w2_salary", "w2_hourly"}
    wages, pay_hourly = _wages(inputs)
    health = _health(inputs, w2)
    retirement = _retirement(inputs, wages, w2)
    taxes = _employer_taxes(inputs, wages, health["employee_total"], w2)
    other = _other_benefits(inputs, w2)
    burden = taxes["total"] + retirement["total"] + health["total"] + other["total"]
    overhead = (wages + burden) * inputs.overhead_pct / 100
    cost = wages + burden + overhead
    hours = inputs.hours
    unbilled = max(inputs.paid_hours - hours, 0) if inputs.pay_type == "w2_salary" else 0
    composition = [
        ("wages", "Pay", wages),
        ("employer_taxes", "Employer taxes", taxes["total"]),
        ("retirement", "401(k) match", retirement["total"]),
        ("health", "Health benefits", health["total"]),
        ("other_benefits", "Other benefits", other["total"]),
        ("overhead", "Overhead and G&A", overhead),
    ]
    notes = []
    if not w2:
        notes.append(f"{PAY_TYPES[inputs.pay_type]} pay carries no employer taxes or company benefits.")
    if inputs.pay_type != "w2_salary" and not inputs.pay_rate:
        notes.append(f"Hourly pay was worked out from the salary over {inputs.paid_hours:,.0f} paid hours.")
    return {
        "tax_year": TAX_YEAR,
        "pay_type": inputs.pay_type,
        "pay_type_label": PAY_TYPES[inputs.pay_type],
        "w2": w2,
        "wages": _r(wages),
        "pay_hourly": _r(pay_hourly),
        "hours": hours,
        "paid_hours": inputs.paid_hours if inputs.pay_type == "w2_salary" else hours,
        "unbilled_hours": unbilled,
        "unbilled_value": _r(unbilled * pay_hourly),
        "employer_taxes": taxes,
        "retirement": retirement,
        "health": health,
        "other_benefits": other,
        "overhead": {"pct": inputs.overhead_pct, "amount": _r(overhead)},
        "burden": {"total": _r(burden), "pct": _r(burden / wages * 100) if wages else 0.0},
        "cost": {"annual": _r(cost), "hourly": _r(cost / hours), "monthly": _r(cost / 12)},
        "billing": _billing(inputs, cost, pay_hourly),
        "employee": _employee(inputs, wages, retirement.get("employee_deferral", 0.0), health["employee_total"]),
        "composition": [
            {"key": key, "label": label, "amount": _r(amount), "pct": _r(amount / cost * 100) if cost else 0.0}
            for key, label, amount in composition
            if amount
        ],
        "notes": notes,
    }


def summary(inputs: BurdenIn) -> dict:
    """The few numbers a pipeline row shows."""
    result = calculate(inputs)
    billing = result["billing"]
    return {
        "bill_rate": billing["bill_rate"],
        "cost_hourly": result["cost"]["hourly"],
        "profit_hourly": billing["profit_hourly"],
        "margin_pct": billing["margin_pct"],
        "status": billing["status"],
    }
