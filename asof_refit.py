"""Refit the report's forecasting model at each as-of month (FAQ 4).

For as-of month M, the model sees only cohort-age cells whose calendar month is
<= M, acquisition spending dated in cohorts <= M, and economics ratios from
those same cells. It reuses the lab's own model code (cohort_lab.model) with the
report's seed, step budget and diagnostic gates; nothing fitted on later data
is reused. Results are written one JSON file per month so runs are resumable.

Run from this folder with the lab's locked environment, for example:
    uv run --frozen --project ../customer-economics-lab python asof_refit.py --months 2024-03 2024-04
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_LAB = HERE.parent / "customer-economics-lab"


def month_list(start: str = "2024-01", end: str = "2025-12") -> list[str]:
    import pandas as pd
    return [str(p)[:7] for p in pd.period_range(start, end, freq="M")]


def refit(lab: Path, run: Path, as_of: str, out_dir: Path, seed: int, steps: int) -> dict:
    sys.path.insert(0, str(lab))
    import numpy as np
    import pandas as pd
    from cohort_lab import model as m

    tables = run / "tables"
    cutoff = pd.Timestamp(as_of + "-01")
    full = m._validate(pd.read_csv(tables / "cohort_age_summary.csv"))
    full["calendar_ts"] = pd.to_datetime(full.calendar_month)
    train = full[full.calendar_ts <= cutoff].drop(columns="calendar_ts").reset_index(drop=True)
    train = m._validate(train)
    costs = pd.read_csv(tables / "cohort_acquisition_costs.csv")
    costs = costs[pd.to_datetime(costs.cohort_month) <= cutoff]
    company = pd.read_csv(tables / "cohort_cash_economics.csv").query("age_month==0")
    company = company[pd.to_datetime(company.cohort_month) <= cutoff].set_index("cohort_month")
    frame_hash = hashlib.sha256(train.to_csv(index=False).encode()).hexdigest()
    record = {"as_of": as_of, "seed": seed, "steps": steps, "training_cells": len(train),
              "training_last_calendar_month": str(train.calendar_month.max()),
              "training_frame_sha256": frame_hash, "model": "cohort_lab.model._posterior (report model)"}
    started = time.time()
    try:
        draws, diag = m._posterior(train, seed, steps)
    except ValueError as exc:  # too little history: the model refuses to fit
        record.update(status="not_fitted", reason=str(exc), elapsed_seconds=round(time.time() - started, 1))
        return record
    gates = {"max_r_hat": diag["max_r_hat"], "min_ess": diag["min_ess"], "divergences": diag["divergences"],
             "retention_pearson_dispersion": diag["retention_pearson_dispersion"],
             "revenue_pearson_dispersion": diag["revenue_pearson_dispersion"],
             "n_retention_cells": diag["n_retention_cells"], "n_revenue_cells": diag["n_revenue_cells"]}
    passed = diag["max_r_hat"] <= 1.01 and diag["min_ess"] >= 400 and diag["divergences"] == 0
    record.update(diagnostics=gates, gates_passed=bool(passed),
                  parameters={r["parameter"]: {k: r[k] for k in ("mean", "p05", "p95")}
                              for r in diag["parameter_summary"] if not r["parameter"].startswith("cohort_z")})
    if not passed:
        record.update(status="failed_gates", reason="Report diagnostic gates failed (R-hat<=1.01, ESS>=400, 0 divergences); forecast withheld",
                      elapsed_seconds=round(time.time() - started, 1))
        return record

    H, D = m.HORIZON, m.DRAWS
    cost_map = costs.set_index(m.KEYS)
    cells, aggregates = [], {}
    for key, g in train.groupby(m.KEYS, sort=True):
        g = g.sort_values("age_month")
        n0 = int(g.n_acquired.iloc[0])
        obs_len = min(len(g), H)
        retained = np.zeros((D, H)); contribution = np.zeros((D, H)); net = np.zeros((D, H))
        retained[:, :obs_len] = g.n_retained.to_numpy()[:obs_len]
        contribution[:, :obs_len] = g.contribution.to_numpy()[:obs_len]
        net[:, :obs_len] = g.net_revenue.to_numpy()[:obs_len]
        observed = np.arange(H) < obs_len
        if obs_len < H:
            ages = list(range(obs_len, H))
            fn, fgross = m._future(draws, g.iloc[-1], ages, float(g.n_retained.iloc[-1]))
            net_ratio, contrib_ratio = m._economic_ratios(train, g.iloc[-1], ages)
            retained[:, obs_len:] = fn
            contribution[:, obs_len:] = fgross * contrib_ratio
            net[:, obs_len:] = fgross * net_ratio
        cost = cost_map.loc[key] if key in cost_map.index else None
        supported = cost is not None and pd.notna(cost.cac)
        spend = float(cost.acquisition_spend) if cost is not None and pd.notna(cost.acquisition_spend) else 0.
        rec = m._valuation_record(key, n0, spend, obs_len, contribution, observed, supported)
        rec.update(channel=key[1], primary_need=key[2])
        cells.append(rec)
        a = aggregates.setdefault(key[0], {"n": 0, "retained": np.zeros((D, H)), "contribution": np.zeros((D, H)),
                                           "net": np.zeros((D, H)), "observed_months": obs_len})
        a["n"] += n0; a["retained"] += retained; a["contribution"] += contribution; a["net"] += net
    cohorts, curves = [], []
    for cohort, a in sorted(aggregates.items()):
        spend = float(company.loc[cohort, "acquisition_spend"])
        if int(company.loc[cohort, "n_acquired"]) != a["n"]:
            raise ValueError("Whole-cohort denominator differs")
        obs = np.arange(H) < a["observed_months"]
        cohorts.append(m._valuation_record((cohort,), a["n"], spend, a["observed_months"], a["contribution"], obs))
        cum = np.cumsum(a["contribution"].mean(axis=0)) - spend
        for age in range(H):
            curves.append({"cohort_month": cohort, "age_month": age, "observed": bool(obs[age]),
                           "retained_share_mean": float(a["retained"][:, age].mean() / a["n"]),
                           "retained_share_p05": float(np.quantile(a["retained"][:, age], .05) / a["n"]),
                           "retained_share_p95": float(np.quantile(a["retained"][:, age], .95) / a["n"]),
                           "net_revenue_per_customer": float(a["net"][:, age].mean() / a["n"]),
                           "contribution_per_customer": float(a["contribution"][:, age].mean() / a["n"]),
                           "cash_after_cac_per_customer": float(cum[age] / a["n"])})

    def clean(rows):
        out = []
        for r in rows:
            out.append({k: (None if isinstance(v, float) and not np.isfinite(v) else
                            int(v) if isinstance(v, (np.integer,)) else
                            float(v) if isinstance(v, (np.floating,)) else
                            bool(v) if isinstance(v, (np.bool_,)) else v) for k, v in r.items()})
        return out
    record.update(status="fitted", cohort_valuation=clean(cohorts), segment_valuation=clean(cells),
                  curves=clean(curves), elapsed_seconds=round(time.time() - started, 1))
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lab", type=Path, default=DEFAULT_LAB)
    ap.add_argument("--run", type=Path, default=None, help="lab output folder (default <lab>/outputs/student)")
    ap.add_argument("--out", type=Path, default=HERE / "output" / "refits")
    ap.add_argument("--months", nargs="*", default=None)
    ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    run = a.run or a.lab / "outputs" / "student"
    a.out.mkdir(parents=True, exist_ok=True)
    for month in a.months or month_list():
        target = a.out / f"{month}.json"
        if target.exists() and not a.force:
            print(f"{month}: exists, skipped", flush=True); continue
        result = refit(a.lab, run, month, a.out, a.seed, a.steps)
        target.write_text(json.dumps(result, indent=1, allow_nan=False) + "\n", encoding="utf-8")
        print(f"{month}: {result['status']} in {result.get('elapsed_seconds')}s", flush=True)


if __name__ == "__main__":
    main()
