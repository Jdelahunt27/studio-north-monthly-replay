"""FAQ 4 follow-up check: rebuild one as-of month from records cut off at that month.

The dashboard replays observed results by filtering the run's saved SQL exports
by calendar month. This script instead truncates the eight raw source files to
records dated before the cutoff (first instant of the following month), reruns
the lab's canonical sql/01_views.sql in DuckDB with data_as_of = cutoff, and
compares the rebuilt tables with the dashboard's filtered view. If they match,
the replay used no information from after the as-of month.

    uv run --frozen --project ../customer-economics-lab python verify_cutoff.py --as-of 2025-03
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_LAB = HERE.parent / "customer-economics-lab"

# Column that dates each record, and the rule that makes it known by the cutoff.
AVAILABLE = {
    "people.csv": "record_created_at < CUTOFF",
    "subscription_periods.csv": "renewal_due_at < CUTOFF",
    "transactions.csv": "occurred_at < CUTOFF",
    "product_events.csv": "occurred_at < CUTOFF",
    "feedback.csv": "submitted_at < CUTOFF",
    "campaign_spend.csv": "spend_date < CUTOFF",
    "acquisition_attribution.csv": "credited_at < CUTOFF",
    "channel_holdouts.csv": "followup_end_at <= CUTOFF",
}


def rebuild(lab: Path, as_of: str):
    sys.path.insert(0, str(lab))
    import duckdb
    import pandas as pd
    from cohort_lab.data import SCHEMAS
    cutoff = (pd.Period(as_of, "M") + 1).start_time.strftime("%Y-%m-%d %H:%M:%S")
    con = duckdb.connect(":memory:")
    con.execute("SET threads=1; SET TimeZone='UTC';")
    con.execute(f"CREATE VIEW lab_settings AS SELECT TIMESTAMP '{cutoff}' AS data_as_of;")
    for name, cols in SCHEMAS.items():
        types = ", ".join(f"'{k}': '{v}'" for k, v in cols.items())
        path = (lab / "data" / name).resolve().as_posix()
        where = AVAILABLE[name].replace("CUTOFF", f"TIMESTAMP '{cutoff}'")
        con.execute(f"CREATE VIEW {Path(name).stem} AS SELECT * FROM read_csv('{path}', header=true, "
                    f"columns={{{types}}}, nullstr='', strict_mode=true) WHERE {where};")
    con.execute((lab / "sql" / "01_views.sql").read_text(encoding="utf-8"))
    out = {t: con.execute(f"SELECT * FROM {t}").df() for t in
           ("cohort_age_summary", "cohort_cash_economics", "channel_cac", "company_totals")}
    con.close()
    return out, cutoff


def compare(rebuilt, saved, keys, cols):
    import numpy as np
    import pandas as pd
    for f in (rebuilt, saved):
        for k in keys:
            f[k] = f[k].astype(str).str[:10]
    a = rebuilt.sort_values(keys).reset_index(drop=True)
    b = saved.sort_values(keys).reset_index(drop=True)
    if len(a) != len(b) or not (a[keys].values == b[keys].values).all():
        return {"rows_rebuilt": len(a), "rows_dashboard": len(b), "match": False, "reason": "different cells"}
    worst = 0.0
    for c in cols:
        x = pd.to_numeric(a[c], errors="coerce").astype(float).to_numpy()
        y = pd.to_numeric(b[c], errors="coerce").astype(float).to_numpy()
        both_nan = np.isnan(x) & np.isnan(y)
        diff = np.where(both_nan, 0, np.abs(x - y))
        worst = max(worst, float(np.nanmax(diff)) if len(diff) else 0.0)
    return {"rows": len(a), "max_abs_difference": worst, "match": worst < 1e-6}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", type=Path, default=DEFAULT_LAB)
    ap.add_argument("--as-of", default="2025-03")
    ap.add_argument("--out", type=Path, default=HERE / "output" / "checks")
    a = ap.parse_args()
    import pandas as pd
    rebuilt, cutoff = rebuild(a.lab, a.as_of)
    tables = a.lab / "outputs" / "student" / "tables"
    month = pd.Timestamp(a.as_of + "-01")
    # The dashboard's view: saved exports filtered to calendar months <= as-of.
    cas = pd.read_csv(tables / "cohort_age_summary.csv")
    cas = cas[pd.to_datetime(cas.calendar_month) <= month]
    cash = pd.read_csv(tables / "cohort_cash_economics.csv")
    cash = cash[pd.to_datetime(cash.calendar_month) <= month]
    # observed_months and first payback must be recomputed inside the cut, as the dashboard does.
    cash = cash.drop(columns=["observed_months", "first_observed_payback_age", "cash_payback_month"])
    cash["observed_months"] = cash.groupby("cohort_month").age_month.transform("count")
    pay = cash[cash.balance_after_acquisition >= 0].groupby("cohort_month").age_month.min()
    cash["first_observed_payback_age"] = cash.cohort_month.map(pay)
    tests = pd.read_csv(tables / "channel_cac.csv")
    tests = tests[pd.to_datetime(tests.followup_end_at) <= pd.Timestamp(cutoff)]
    comp = pd.read_csv(tables / "company_totals.csv")
    comp = comp[pd.to_datetime(comp.calendar_month) <= month]
    report = {"as_of": a.as_of, "cutoff_exclusive": cutoff, "rules": AVAILABLE, "tables": {
        "cohort_age_summary": compare(rebuilt["cohort_age_summary"], cas,
            ["cohort_month", "channel", "primary_need", "age_month"],
            ["n_acquired", "n_retained", "n_paying", "orders", "gross_payment_revenue", "net_revenue", "variable_cost", "contribution"]),
        "cohort_cash_economics": compare(rebuilt["cohort_cash_economics"], cash, ["cohort_month", "age_month"],
            ["n_acquired", "acquisition_spend", "cac", "cumulative_contribution", "balance_after_acquisition",
             "observed_months", "first_observed_payback_age"]),
        "company_totals": compare(rebuilt["company_totals"], comp, ["calendar_month"],
            ["n_retained", "net_revenue", "contribution", "acquisition_spend"]),
        "channel_cac_completed_tests": compare(rebuilt["channel_cac"], tests, ["test_id"],
            ["buyers_treatment", "buyers_control", "incremental_buyers", "icac"]),
    }}
    report["all_match"] = all(t["match"] for t in report["tables"].values())
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"cutoff-rebuild-{a.as_of}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
