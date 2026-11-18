"""Build the month-by-month replay dashboard (FAQ 4) as one self-contained HTML file.

Inputs (never modified):
  <lab>/outputs/student/tables/*.csv   saved SQL exports and report tables from the lab run
  output/refits/YYYY-MM.json            as-of refits written by asof_refit.py
Outputs:
  output/studio-north-monthly-replay.html   the dashboard (open in any browser, works offline)
  output/replay_data.json                    the precomputed monthly payload embedded in it
  output/checks/reconciliation.json          Dec 2025 replay vs the original report tables
  output/checks/faq4_answers.json            computed answers to FAQ 4's two questions

    uv run --frozen --project ../customer-economics-lab python build_dashboard.py
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_LAB = HERE.parent / "customer-economics-lab"
SEGMENTS = [("search", "build_skill"), ("search", "save_time"), ("partner", "build_skill"), ("partner", "save_time")]
SEG_LABEL = {s: f"{s[0].title()} / {s[1].replace('_', ' ')}" for s in SEGMENTS}
DISCOUNT, HORIZON = 0.01, 12


def num(x, nd=4):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(x) else round(x, nd)


def month_str(ts) -> str:
    return str(ts)[:7]


def build(lab: Path, run: Path, refit_dir: Path):
    t = run / "tables"
    totals = pd.read_csv(t / "cohort_totals.csv")
    cas = pd.read_csv(t / "cohort_age_summary.csv")
    cash = pd.read_csv(t / "cohort_cash_economics.csv")
    company = pd.read_csv(t / "company_totals.csv")
    tests = pd.read_csv(t / "channel_cac.csv")
    report_val = pd.read_csv(t / "cohort_valuation.csv")
    report_dec = pd.read_csv(t / "channel_value_decision.csv")
    for f in (totals, cas, cash, company):
        f["cal"] = pd.to_datetime(f.calendar_month)
    tests["end"] = pd.to_datetime(tests.followup_end_at)
    months = [str(p) for p in pd.period_range("2024-01", "2025-12", freq="M")]
    refits = {}
    for m in months:
        p = refit_dir / f"{m}.json"
        refits[m] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"as_of": m, "status": "missing"}

    payload, prev = [], None
    for m in months:
        cut_month = pd.Timestamp(m + "-01")
        cutoff = (pd.Period(m, "M") + 1).start_time  # exclusive instant: end of the as-of month
        tt = totals[totals.cal <= cut_month]
        cohorts = sorted(tt.cohort_month.unique())
        triangle = {c[:7]: [num(v, 4) for v in g.sort_values("age_month").retained_share] for c, g in tt.groupby("cohort_month")}
        mix = {}
        for c, g in cas[(cas.age_month == 0) & (cas.cal <= cut_month)].groupby("cohort_month"):
            mix[c[:7]] = {f"{r.channel}|{r.primary_need}": int(r.n_acquired) for r in g.itertuples()}
        cc = cash[cash.cal <= cut_month]
        rf = refits[m]
        fitted = rf.get("status") == "fitted"
        val_by = {r["cohort_month"][:7]: r for r in rf.get("cohort_valuation", [])} if fitted else {}
        curves = {}
        if fitted:
            for r in rf["curves"]:
                curves.setdefault(r["cohort_month"][:7], []).append(r)
        rows = []
        for c, g in cc.groupby("cohort_month"):
            g = g.sort_values("age_month")
            n = int(g.n_acquired.iloc[0]); cac = float(g.cac.iloc[0])
            obs = len(g)
            paid = g[g.balance_after_acquisition >= 0]
            tg = tt[tt.cohort_month == c].sort_values("age_month")
            contrib = tg.contribution.to_numpy(float)[:HORIZON]
            obs_value = float(np.sum(contrib / (1 + DISCOUNT) ** np.arange(1, len(contrib) + 1)) / n)
            row = {"cohort": c[:7], "n": n, "cac": num(cac, 2), "observed_months": obs,
                   "cash_after_cac": num(g.balance_per_customer.iloc[-1], 2),
                   "observed_payback_month": int(paid.age_month.min()) + 1 if len(paid) else None,
                   "retained_latest": num(tg.retained_share.iloc[-1], 4),
                   "observed_value_to_date": num(obs_value, 2),
                   "age5": None if obs < 6 else {"retained": num(tg.retained_share.iloc[5], 4),
                       "contribution_per_customer": num(g.cumulative_contribution_per_customer.iloc[5], 2),
                       "cash_after_cac": num(g.balance_per_customer.iloc[5], 2)}}
            v = val_by.get(c[:7])
            if v:
                row["ltv"] = {"mean": num(v["ltv_before_cac_mean"], 2), "p05": num(v["ltv_before_cac_p05"], 2),
                              "p95": num(v["ltv_before_cac_p95"], 2), "net": num(v["net_ltv_mean"], 2),
                              "ratio": num(v["ltv_to_cac_mean"], 3), "forecast_share": num(v["forecast_share"], 3),
                              "observed_part": num(v["observed_discounted_contribution_per_customer"], 2),
                              "payback_month": v["payback_month"], "payback_status": v["payback_status"]}
                row["path"] = [{"age": r["age_month"], "obs": r["observed"], "ret": num(r["retained_share_mean"], 4),
                                "cash": num(r["cash_after_cac_per_customer"], 2)} for r in curves.get(c[:7], [])]
            rows.append(row)
        comp = company[company.cal <= cut_month]
        comp_series = [{"month": month_str(r.calendar_month), "members": int(r.n_retained), "net_revenue": num(r.net_revenue, 2),
                        "contribution": num(r.contribution, 2), "spend": num(r.acquisition_spend, 2)} for r in comp.itertuples()]
        done = tests[tests.end <= cutoff]
        waves = [{"test": r.test_id, "wave": month_str(r.test_month), "cell": f"{r.channel}|{r.primary_need}",
                  "buyers_t": int(r.buyers_treatment), "buyers_c": int(r.buyers_control), "incremental": num(r.incremental_buyers, 1),
                  "credited_cac": num(r.credited_cac, 2), "icac": num(r.icac, 2), "lo": num(r.icac_ci_lower, 2), "hi": num(r.icac_ci_upper, 2)}
                 for r in done.sort_values(["test_month", "channel", "primary_need"]).itertuples()]
        decision = None
        if len(done) and fitted:
            seg = pd.DataFrame(rf["segment_valuation"])
            seg["cohort"] = seg.cohort_month.str[:7]
            full = seg[seg.observed_months >= 6]
            ok = full.groupby("cohort").apply(lambda d: {(r.channel, r.primary_need) for r in d.itertuples()} >= set(SEGMENTS), include_groups=False)
            bench = max([c for c, v in ok.items() if v], default=None)
            if bench:
                latest = done.sort_values("end").groupby(["channel", "primary_need"]).tail(1)
                cells = []
                for ch, need in SEGMENTS:
                    tl = latest[(latest.channel == ch) & (latest.primary_need == need)]
                    sv = seg[(seg.cohort == bench) & (seg.channel == ch) & (seg.primary_need == need)]
                    if tl.empty or sv.empty:
                        continue
                    value = float(sv.ltv_before_cac_mean.iloc[0]); icac = float(tl.icac.iloc[0])
                    cells.append({"cell": f"{ch}|{need}", "test": tl.test_id.iloc[0], "wave": month_str(tl.test_month.iloc[0]),
                                  "icac": num(icac, 2), "icac_lo": num(tl.icac_ci_lower.iloc[0], 2), "icac_hi": num(tl.icac_ci_upper.iloc[0], 2),
                                  "value": num(value, 2), "forecast_share": num(sv.forecast_share.iloc[0], 3),
                                  "value_less_icac": num(value - icac, 2), "ratio": num(value / icac, 3),
                                  "incremental": num(tl.incremental_buyers.iloc[0], 1),
                                  "planning_net": num((value - icac) * float(tl.incremental_buyers.iloc[0]), 0)})
                decision = {"benchmark_cohort": bench, "cells": cells}
        model = {"status": rf.get("status"), "reason": rf.get("reason"), "training_last": rf.get("training_last_calendar_month", "")[:7],
                 "diagnostics": rf.get("diagnostics"), "elapsed": rf.get("elapsed_seconds"),
                 "params": {k: rf["parameters"][k] for k in ("mean_beta[build_skill]", "mean_beta[partner]", "mean_beta[cohort_trend]")}
                 if rf.get("parameters") else None}
        cur = {"rows": {r["cohort"]: r for r in rows}, "waves": len(waves)}
        changes = []
        if prev is None:
            changes.append(f"First cohort joins: {cohorts[-1][:7]} with {rows[-1]['n']} paying customers; nothing to compare yet.")
        else:
            newc = [c for c in cur["rows"] if c not in prev["rows"]]
            for c in newc:
                r = cur["rows"][c]
                changes.append(f"New cohort {c}: {r['n']} customers acquired at a historical average CAC of ${r['cac']:.0f}.")
            for c, r in cur["rows"].items():
                p = prev["rows"].get(c)
                if p and p["observed_payback_month"] is None and r["observed_payback_month"] is not None:
                    changes.append(f"Cohort {c} paid back its acquisition cost (observed, month {r['observed_payback_month']}).")
            if cur["waves"] > prev["waves"]:
                changes.append(f"{cur['waves'] - prev['waves']} acquisition holdout tests completed; iCAC updated.")
            if model["status"] == "fitted" and prev["model"] != "fitted":
                changes.append("First month with enough renewal history to fit the forecast model.")
        cur["model"] = model["status"]
        prev = cur
        payload.append({"month": m, "cutoff": str(cutoff)[:10], "triangle": triangle, "mix": mix, "cohorts": rows,
                        "company": comp_series, "waves": waves, "decision": decision, "model": model, "changes": changes})

    # Reconciliation: the final as-of month should reproduce the report's tables (and therefore its PDF).
    final = refits[months[-1]]
    recon = {"as_of": months[-1], "refit_status": final.get("status")}
    if final.get("status") == "fitted":
        mine = pd.DataFrame(final["cohort_valuation"]).set_index("cohort_month")
        theirs = report_val.set_index("cohort_month")
        cols = ["ltv_before_cac_mean", "ltv_before_cac_p05", "ltv_before_cac_p95", "net_ltv_mean", "cac", "forecast_share"]
        diffs = {c: float(np.nanmax(np.abs(mine.loc[theirs.index, c].astype(float) - theirs[c].astype(float)))) for c in cols}
        pay = bool((mine.loc[theirs.index, "payback_month"].fillna(-1).astype(int).values ==
                    theirs.payback_month.fillna(-1).astype(int).values).all())
        dec = {c["cell"]: c for c in payload[-1]["decision"]["cells"]} if payload[-1]["decision"] else {}
        ddiff = {}
        for r in report_dec.itertuples():
            k = f"{r.channel}|{r.primary_need}"
            if k in dec:
                ddiff[k] = {"value_less_icac_report": round(r.value_less_icac, 2), "value_less_icac_replay": dec[k]["value_less_icac"],
                            "abs_difference": round(abs(r.value_less_icac - dec[k]["value_less_icac"]), 4)}
        recon.update(cohort_valuation_max_abs_difference=diffs, payback_months_identical=pay,
                     decision=ddiff, benchmark_cohort=payload[-1]["decision"]["benchmark_cohort"] if payload[-1]["decision"] else None)
        recon["matches_report"] = max(diffs.values()) < 0.01 and pay and all(v["abs_difference"] < 0.01 for v in ddiff.values())

    # FAQ 4 questions, computed from the replay itself.
    final_signs = {c["cell"]: c["value_less_icac"] > 0 for c in payload[-1]["decision"]["cells"]} if payload[-1]["decision"] else {}
    timeline = []
    for p in payload:
        d = p["decision"]
        if not d or len(d["cells"]) < 4:
            continue
        signs = {c["cell"]: c["value_less_icac"] > 0 for c in d["cells"]}
        robust = next((c["value"] > c["icac_hi"] for c in d["cells"] if c["cell"] == "search|build_skill"), False)
        timeline.append({"month": p["month"], "benchmark_cohort": d["benchmark_cohort"], "pattern_matches_report": signs == final_signs,
                         "search_build_skill_clears_upper_icac": robust,
                         "value_less_icac": {c["cell"]: c["value_less_icac"] for c in d["cells"]}})
    first_match = next((x["month"] for x in timeline if x["pattern_matches_report"]), None)
    stable = None
    for i, x in enumerate(timeline):
        if all(y["pattern_matches_report"] for y in timeline[i:]):
            stable = x["month"]; break
    first_robust = next((x["month"] for x in timeline if x["pattern_matches_report"] and x["search_build_skill_clears_upper_icac"]), None)
    trend = []
    for p in payload:
        vals = [r for r in p["cohorts"] if r.get("ltv")]
        if not vals:
            continue
        early = [r for r in vals if r["cohort"] <= "2024-03"]
        recent = sorted(vals, key=lambda r: r["cohort"])[-3:]
        trend.append({"month": p["month"], "early_2024_ratio": num(np.mean([r["ltv"]["ratio"] for r in early]), 3) if early else None,
                      "latest_three_ratio": num(np.mean([r["ltv"]["ratio"] for r in recent]), 3),
                      "latest_three": [r["cohort"] for r in recent],
                      "latest_three_forecast_share": num(np.mean([r["ltv"]["forecast_share"] for r in recent]), 3)})
    answers = {"decision_timeline": timeline, "first_month_pattern_matches_report": first_match,
               "first_month_pattern_stable_through_dec_2025": stable,
               "first_month_matching_with_search_build_skill_above_upper_icac": first_robust,
               "value_to_cac_trend": trend,
               "note": "Report recommendation pattern = value-before-CAC exceeds current iCAC for both build-skill cells and falls short for both save-time cells. Acquisition holdouts begin with the July 2025 wave, so no earlier month can support an iCAC-based allocation."}
    return payload, recon, answers


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Studio North Monthly Replay</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--good:#006300;--bad:#d03b3b;--seq0:#cde2fb;--seq1:#104281;--fc:#86b6ef;}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--good:#0ca30c;--bad:#e66767;--seq0:#1c2a3a;--seq1:#86b6ef;--fc:#256abf;}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--good:#0ca30c;--bad:#e66767;--seq0:#1c2a3a;--seq1:#86b6ef;--fc:#256abf;}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--surface);border-bottom:1px solid var(--ring);padding:12px 16px}
.wrap{max-width:1240px;margin:0 auto;padding:0 16px}
h1{font-size:18px;margin:0}h2{font-size:15px;margin:0 0 4px}.sub{color:var(--ink2);font-size:13px}
.ctrl{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:8px}
button{font:inherit;border:1px solid var(--ring);background:var(--page);color:var(--ink);border-radius:6px;padding:5px 10px;cursor:pointer}
button:hover{background:var(--grid)}input[type=range]{flex:1;min-width:180px}
.asof{font-weight:700;font-size:16px;min-width:150px}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px;margin:12px 0}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px;min-width:0}
.c12{grid-column:span 12}.c8{grid-column:span 8}.c6{grid-column:span 6}.c4{grid-column:span 4}
@media(max-width:900px){.c8,.c6,.c4{grid-column:span 12}}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile .v{font-size:22px;font-weight:650}.tile .l{color:var(--ink2);font-size:12px}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:9px;border:1px solid var(--ring);color:var(--ink2)}
.obs{border-color:var(--s1)}.fc{border-style:dashed}
table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}th,td{padding:3px 6px;text-align:right;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
.scroll{overflow-x:auto}.neg{color:var(--bad)}.pos{color:var(--good)}
ul.changes{margin:4px 0 0 18px;padding:0}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--ink2);margin:4px 0}.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
svg text{fill:var(--ink2);font-size:11px}.tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:6px;padding:6px 8px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.15);display:none;z-index:9}
.note{color:var(--ink2);font-size:12px}.blank{color:var(--muted);font-style:italic}
details summary{cursor:pointer;color:var(--ink2)}
</style></head><body>
<header><div class="wrap">
<h1>Studio North · month-by-month replay of the customer-economics report</h1>
<div class="sub">Each view shows only what Studio North could have known at the end of the selected month. Solid = observed; dashed/hatched = model forecast refitted on data through that month.</div>
<div class="ctrl"><button id="first" title="Jan 2024">⏮</button><button id="prev" title="Previous month (←)">◀ Prev</button>
<span class="asof" id="asof"></span><button id="next" title="Next month (→)">Next ▶</button><button id="last" title="Dec 2025">⏭</button>
<button id="play">▶ Play</button><input id="slider" type="range" min="0" max="23" value="0" aria-label="As-of month">
<button id="theme" title="Toggle light/dark">◐</button></div></div></header>
<main class="wrap">
<div class="grid">
<section class="card c12"><h2>What changed this month</h2><ul class="changes" id="changes"></ul></section>
<section class="card c12"><div class="tiles" id="tiles"></div></section>
<section class="card c6"><h2>Retention triangle <span class="tag obs">observed</span></h2><div class="sub">% of each cohort's original customers still paying, by months since first payment. Blank = not yet happened.</div><div class="scroll" id="tri"></div></section>
<section class="card c6"><h2>Cohort mix by channel × need <span class="tag obs">observed</span></h2><div class="legend" id="mixlegend"></div><div id="mix"></div></section>
<section class="card c12"><h2>12-receipt contribution value vs. CAC, per customer</h2>
<div class="legend"><span><span class="sw" style="background:var(--s1)"></span>Observed contribution (discounted)</span><span><span class="sw" style="background:repeating-linear-gradient(45deg,var(--fc) 0 2px,transparent 2px 5px);border:1px dashed var(--s1)"></span>Forecast remainder (as-of refit)</span><span><span class="sw" style="background:var(--ink)"></span>Historical average CAC</span><span>Whiskers: 5th–95th percentile (parameter uncertainty only)</span></div>
<div id="ltv"></div><div class="note" id="ltvnote"></div>
<details><summary>Table view</summary><div class="scroll" id="ltvtable"></div></details></section>
<section class="card c8"><h2>Company by calendar month <span class="tag obs">observed</span></h2><div class="legend"><span><span class="sw" style="background:var(--s1)"></span>Net revenue</span><span><span class="sw" style="background:var(--s3)"></span>Contribution</span><span><span class="sw" style="background:var(--s2)"></span>Acquisition spend</span></div><div id="comp"></div><div class="note">All series in USD per month. Excludes fixed operating costs and the separate holdout research budget.</div></section>
<section class="card c4"><h2>Forecast model at this month</h2><div id="model"></div></section>
<section class="card c12"><h2>Acquisition decision: value before CAC vs. current iCAC</h2><div id="decision"></div></section>
<section class="card c12"><h2>Reconciliation and FAQ 4 answers</h2><div id="recon"></div></section>
</div>
<p class="note">Definitions follow the report: cohort = first successful paid month; age 0 = acquisition month; retention uses paid subscription periods over the original acquired-customer denominator; contribution = net revenue (after discounts and refunds) minus variable costs; LTV = 12 monthly receipts of contribution discounted 1%/month (t = age+1), before CAC; net value subtracts historical average CAC once; payback = first month cumulative undiscounted contribution ≥ CAC. iCAC uses only holdout waves whose 31-day window ended by the as-of cutoff. Forecasts come from the report's hierarchical sBG + Gamma model refitted with seed 20261116 on cells dated through the as-of month only.</p>
</main><div class="tip" id="tip"></div>
<script>
const DATA=__DATA__, RECON=__RECON__, ANS=__ANS__;
const SEG=[["search|build_skill","Search / build skill","--s1"],["search|save_time","Search / save time","--s2"],["partner|build_skill","Partner / build skill","--s3"],["partner|save_time","Partner / save time","--s4"]];
const $=id=>document.getElementById(id), css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fm=v=>v==null?"–":(v<0?"−$":"$")+Math.abs(v).toLocaleString(undefined,{maximumFractionDigits:0});
const f2=v=>v==null?"–":(v<0?"−$":"$")+Math.abs(v).toFixed(2), pc=v=>v==null?"–":(100*v).toFixed(1)+"%";
const mname=m=>new Date(m+"-15").toLocaleString("en-US",{month:"short",year:"numeric"});
let idx=0,timer=null;const tip=$("tip");
function showTip(e,h){tip.innerHTML=h;tip.style.display="block";tip.style.left=Math.min(e.clientX+12,innerWidth-260)+"px";tip.style.top=(e.clientY+12)+"px"}
function hideTip(){tip.style.display="none"}
function el(tag,attrs,parent){const n=document.createElementNS("http://www.w3.org/2000/svg",tag);for(const k in attrs)n.setAttribute(k,attrs[k]);if(parent)parent.appendChild(n);return n}
function bindTip(n,h){n.addEventListener("mousemove",e=>showTip(e,h));n.addEventListener("mouseleave",hideTip)}
function render(){const d=DATA[idx];$("asof").textContent="As of end of "+mname(d.month);$("slider").value=idx;
 $("changes").innerHTML=d.changes.map(c=>"<li>"+c+"</li>").join("")||"<li class=blank>No new cohort, payback or test this month.</li>";
 const c=d.company[d.company.length-1], last=d.cohorts[d.cohorts.length-1], paid=d.cohorts.filter(r=>r.observed_payback_month!=null).length;
 const tiles=[["Paying members",c.members.toLocaleString(),"observed, month "+d.month],["Net revenue",fm(c.net_revenue),"this month, observed"],["Contribution",fm(c.contribution),"this month, observed"],["Acquisition spend",fm(c.spend),"this month, observed"],["Newest cohort CAC",f2(last.cac),last.cohort+", historical average"],["Cohorts paid back",paid+" of "+d.cohorts.length,"observed cash ≥ CAC"]];
 $("tiles").innerHTML=tiles.map(t=>`<div class="tile"><div class="l">${t[0]}</div><div class="v">${t[1]}</div><div class="l">${t[2]}</div></div>`).join("");
 tri(d);mix(d);ltv(d);comp(d);model(d);decision(d);recon(d)}
function tri(d){const cs=Object.keys(d.triangle),W=24,H=16,L=58,T=18,maxA=24;const s=el("svg",{viewBox:`0 0 ${L+maxA*W+4} ${T+cs.length*H+4}`,width:"100%"});
 for(let a=0;a<maxA;a+=3)el("text",{x:L+a*W+W/2,y:12,"text-anchor":"middle"},s).textContent=a;
 cs.forEach((k,i)=>{el("text",{x:L-6,y:T+i*H+12,"text-anchor":"end"},s).textContent=k;d.triangle[k].forEach((v,a)=>{const t=Math.max(0,Math.min(1,(v-.2)/.8));
  const r=el("rect",{x:L+a*W+1,y:T+i*H+1,width:W-2,height:H-2,rx:2,fill:mixc(css("--seq0"),css("--seq1"),t)},s);bindTip(r,`<b>${k}</b>, age ${a}<br>${pc(v)} retained (observed)`);
  if(a%3==0||a==d.triangle[k].length-1){const tx=el("text",{x:L+a*W+W/2,y:T+i*H+11.5,"text-anchor":"middle","font-size":"9"},s);tx.textContent=Math.round(100*v);tx.style.fill=t>.5?"#fff":css("--ink");tx.style.pointerEvents="none"}})});
 $("tri").replaceChildren(s)}
function mixc(a,b,t){const p=h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16));const x=p(a),y=p(b);return"rgb("+x.map((v,i)=>Math.round(v+(y[i]-v)*t)).join(",")+")"}
function mix(d){$("mixlegend").innerHTML=SEG.map(s=>`<span><span class="sw" style="background:var(${s[2]})"></span>${s[1]}</span>`).join("");
 const cs=Object.keys(d.mix),H=14,L=58,W=420;const s=el("svg",{viewBox:`0 0 ${L+W+40} ${cs.length*H+20}`,width:"100%"});
 cs.forEach((k,i)=>{const m=d.mix[k],tot=SEG.reduce((a,g)=>a+(m[g[0]]||0),0);let x=L;el("text",{x:L-6,y:i*H+11,"text-anchor":"end"},s).textContent=k;
  SEG.forEach(g=>{const v=m[g[0]]||0,w=W*v/tot;const r=el("rect",{x:x+1,y:i*H+2,width:Math.max(0,w-2),height:H-4,rx:2,fill:css(g[2])},s);bindTip(r,`<b>${k}</b> · ${g[1]}<br>${v} customers (${(100*v/tot).toFixed(0)}%)`);x+=w});
  el("text",{x:L+W+4,y:i*H+11},s).textContent=tot});
 const bs=d.cohorts.map(r=>r.cohort);$("mix").replaceChildren(s)}
function ltv(d){const rows=d.cohorts,L=46,B=26,W=1100,Hh=230,bw=W/24;const max=Math.max(320,...rows.map(r=>r.ltv?r.ltv.p95:r.observed_value_to_date),...rows.map(r=>r.cac));const y=v=>Hh-B-(Hh-B-10)*v/max;
 const s=el("svg",{viewBox:`0 0 ${L+W} ${Hh}`,width:"100%"});const defs=el("defs",{},s);const pat=el("pattern",{id:"hat",width:5,height:5,patternUnits:"userSpaceOnUse",patternTransform:"rotate(45)"},defs);el("rect",{width:2,height:5,fill:css("--fc")},pat);
 for(let v=0;v<=max;v+=100){el("line",{x1:L,x2:L+W,y1:y(v),y2:y(v),stroke:css("--grid")},s);el("text",{x:L-4,y:y(v)+4,"text-anchor":"end"},s).textContent="$"+v}
 rows.forEach((r,i)=>{const x=L+i*bw+4,w=bw-8;const obsv=r.ltv?r.ltv.observed_part:r.observed_value_to_date;
  const o=el("rect",{x,y:y(obsv),width:w,height:Math.max(0,y(0)-y(obsv)),fill:css("--s1"),rx:3},s);
  let tipH=`<b>Cohort ${r.cohort}</b> (${r.n} customers)<br>Observed discounted contribution: ${f2(obsv)} (${r.observed_months} of 12 receipts)<br>CAC (historical avg): ${f2(r.cac)}`;
  if(r.ltv){const f=el("rect",{x,y:y(r.ltv.mean),width:w,height:Math.max(0,y(obsv)-y(r.ltv.mean)-1),fill:"url(#hat)",stroke:css("--s1"),"stroke-dasharray":"3 2",rx:3},s);
   el("line",{x1:x+w/2,x2:x+w/2,y1:y(r.ltv.p05),y2:y(r.ltv.p95),stroke:css("--ink2")},s);
   tipH+=`<br>12-receipt value: ${f2(r.ltv.mean)} [${f2(r.ltv.p05)}–${f2(r.ltv.p95)}], ${pc(r.ltv.forecast_share)} forecast<br>Net value: ${f2(r.ltv.net)} · value/CAC ${r.ltv.ratio.toFixed(2)}×<br>Payback month ${r.ltv.payback_month??"not in 12"} (${r.ltv.payback_status})`;bindTip(f,tipH)}
  el("line",{x1:x-2,x2:x+w+2,y1:y(r.cac),y2:y(r.cac),stroke:css("--ink"),"stroke-width":2},s);bindTip(o,tipH);
  if(i%2==0||rows.length<13)el("text",{x:x+w/2,y:Hh-8,"text-anchor":"middle"},s).textContent=r.cohort.slice(2)});
 $("ltv").replaceChildren(s);
 $("ltvnote").innerHTML=d.model.status=="fitted"?`Forecast remainder from the model refitted on data through ${d.model.training_last}. Cohorts with 12+ observed months show no forecast.`:`<span class="blank">No forecast this month: ${d.model.reason||"model not fitted"}. Bars show observed discounted contribution to date only.</span>`;
 $("ltvtable").innerHTML="<table><tr><th>Cohort</th><th>Customers</th><th>CAC</th><th>Obs. months</th><th>Observed value</th><th>12-receipt value</th><th>5–95%</th><th>Forecast share</th><th>Net value</th><th>Value/CAC</th><th>Payback</th><th>Cash after CAC now</th></tr>"+
 rows.map(r=>`<tr><td>${r.cohort}</td><td>${r.n}</td><td>${f2(r.cac)}</td><td>${r.observed_months}</td><td>${f2(r.ltv?r.ltv.observed_part:r.observed_value_to_date)}</td><td>${r.ltv?f2(r.ltv.mean):"–"}</td><td>${r.ltv?f2(r.ltv.p05)+"–"+f2(r.ltv.p95):"–"}</td><td>${r.ltv?pc(r.ltv.forecast_share):"–"}</td><td class="${r.ltv&&r.ltv.net<0?"neg":""}">${r.ltv?f2(r.ltv.net):"–"}</td><td>${r.ltv?r.ltv.ratio.toFixed(2)+"×":"–"}</td><td>${r.observed_payback_month?("month "+r.observed_payback_month+" (observed)"):(r.ltv&&r.ltv.payback_month?("month "+r.ltv.payback_month+" (forecast)"):"not yet")}</td><td class="${r.cash_after_cac<0?"neg":"pos"}">${f2(r.cash_after_cac)}</td></tr>`).join("")+"</table>"}
function comp(d){const rows=d.company,L=56,B=22,W=700,H=200,bw=W/24;const max=Math.max(...rows.map(r=>r.net_revenue),40000);const y=v=>H-B-(H-B-8)*v/max;const s=el("svg",{viewBox:`0 0 ${L+W} ${H}`,width:"100%"});
 for(let v=0;v<=max;v+=50000){el("line",{x1:L,x2:L+W,y1:y(v),y2:y(v),stroke:css("--grid")},s);el("text",{x:L-4,y:y(v)+4,"text-anchor":"end"},s).textContent="$"+(v/1000)+"k"}
 rows.forEach((r,i)=>{const x=L+i*bw;const a=el("rect",{x:x+2,y:y(r.net_revenue),width:bw/2-3,height:y(0)-y(r.net_revenue),fill:css("--s1"),rx:2},s);const b=el("rect",{x:x+bw/2,y:y(r.contribution),width:bw/2-3,height:y(0)-y(r.contribution),fill:css("--s3"),rx:2},s);
  const h=`<b>${r.month}</b><br>Members ${r.members}<br>Net revenue ${fm(r.net_revenue)}<br>Contribution ${fm(r.contribution)}<br>Acquisition spend ${fm(r.spend)}`;bindTip(a,h);bindTip(b,h);if(i%3==0)el("text",{x:x+bw/2,y:H-6,"text-anchor":"middle"},s).textContent=r.month.slice(2)});
 const pts=rows.map((r,i)=>`${L+i*bw+bw/2},${y(r.spend)}`).join(" ");el("polyline",{points:pts,fill:"none",stroke:css("--s2"),"stroke-width":2},s);
 rows.forEach((r,i)=>el("circle",{cx:L+i*bw+bw/2,cy:y(r.spend),r:3,fill:css("--s2"),stroke:css("--surface"),"stroke-width":2},s));$("comp").replaceChildren(s)}
function model(d){const m=d.model;if(m.status!="fitted"){$("model").innerHTML=`<p class="blank">Not fitted: ${m.reason||m.status}</p><p class="note">FAQ 4: if history is too short to fit, the forecast is left blank. Only observed results are shown.</p>`;return}
 const g=m.diagnostics,p=m.params;$("model").innerHTML=`<table><tr><td>Training data through</td><td>${m.training_last}</td></tr><tr><td>Renewal cells</td><td>${g.n_retention_cells}</td></tr><tr><td>Max R-hat (≤1.01)</td><td>${g.max_r_hat.toFixed(4)}</td></tr><tr><td>Min ESS (≥400)</td><td>${Math.round(g.min_ess)}</td></tr><tr><td>Divergences (0)</td><td>${g.divergences}</td></tr>
 <tr><td>Build-skill → churn</td><td>${p["mean_beta[build_skill]"].mean.toFixed(2)} [${p["mean_beta[build_skill]"].p05.toFixed(2)}, ${p["mean_beta[build_skill]"].p95.toFixed(2)}]</td></tr><tr><td>Partner → churn</td><td>${p["mean_beta[partner]"].mean.toFixed(2)} [${p["mean_beta[partner]"].p05.toFixed(2)}, ${p["mean_beta[partner]"].p95.toFixed(2)}]</td></tr><tr><td>Cohort trend → churn</td><td>${p["mean_beta[cohort_trend]"].mean.toFixed(2)} [${p["mean_beta[cohort_trend]"].p05.toFixed(2)}, ${p["mean_beta[cohort_trend]"].p95.toFixed(2)}]</td></tr></table><p class="note">Negative = lower churn. Refit used only cells dated through ${m.training_last}; it took ${m.elapsed}s.</p>`}
function decision(d){const w=d.waves;if(!w.length){$("decision").innerHTML=`<p class="blank">No acquisition holdout had completed by ${d.cutoff}. The first monthly wave starts July 2025, so before then only historical average CAC is known — it includes customers who would have joined anyway and cannot price an additional customer.</p>`;return}
 let h="";if(d.decision){h+=`<p class="note">Value = 12-receipt contribution before CAC for the <b>${d.decision.benchmark_cohort}</b> cohort (latest with six observed receipts in every tested cell), estimated at this as-of month. Cost = latest completed iCAC per cell. Assumes additional customers are worth the cohort average.</p><table><tr><th>Cell</th><th>Latest test</th><th>iCAC [95% CI]</th><th>Value before CAC</th><th>Forecast share</th><th>Value − iCAC</th><th>Value ÷ iCAC</th><th>Planning net for $11k test</th></tr>`+
 d.decision.cells.map(c=>`<tr><td><span class="sw" style="background:var(${SEG.find(s=>s[0]==c.cell)[2]})"></span>${SEG.find(s=>s[0]==c.cell)[1]}</td><td>${c.wave}</td><td>${f2(c.icac)} [${f2(c.icac_lo)}–${f2(c.icac_hi)}]</td><td>${f2(c.value)}</td><td>${pc(c.forecast_share)}</td><td class="${c.value_less_icac<0?"neg":"pos"}">${c.value_less_icac<0?"▼ ":"▲ "}${f2(c.value_less_icac)}</td><td>${c.ratio.toFixed(2)}×</td><td class="${c.planning_net<0?"neg":"pos"}">${fm(c.planning_net)}</td></tr>`).join("")+"</table>"}
 else h+=`<p class="blank">Tests completed, but no forecast model is available this month to value the benchmark cohort.</p>`;
 h+=`<details><summary>All ${w.length} completed holdout tests</summary><div class="scroll"><table><tr><th>Wave</th><th>Cell</th><th>Buyers T / C</th><th>Incremental</th><th>Credited CAC</th><th>iCAC [95% CI]</th></tr>`+w.map(t=>`<tr><td>${t.wave}</td><td>${SEG.find(s=>s[0]==t.cell)[1]}</td><td>${t.buyers_t} / ${t.buyers_c}</td><td>${t.incremental}</td><td>${f2(t.credited_cac)}</td><td>${f2(t.icac)} [${f2(t.lo)}–${f2(t.hi)}]</td></tr>`).join("")+"</table></div></details>";$("decision").innerHTML=h}
function recon(d){const last=d.month==DATA[DATA.length-1].month;let h="";
 if(last){h+=`<p><b>Reconciliation to the PDF baseline.</b> ${RECON.matches_report?"✔ The Dec 2025 replay reproduces the report's tables":"✖ The Dec 2025 replay differs from the report's tables"}: largest cohort-value difference $${Math.max(...Object.values(RECON.cohort_valuation_max_abs_difference||{0:0})).toFixed(4)}, payback months ${RECON.payback_months_identical?"identical":"differ"}, decision cells ${Object.entries(RECON.decision||{}).map(([k,v])=>SEG.find(s=>s[0]==k)[1]+" Δ"+v.abs_difference).join(", ")}.</p>`}
 else h+=`<p class="note">Advance to Dec 2025 to see the reconciliation with the original report.</p>`;
 h+=`<p><b>Are newer cohorts' economics improving?</b> ${ANS.value_to_cac_trend.length?`At ${mname(ANS.value_to_cac_trend[0].month)} the first fitted model valued the Jan–Mar 2024 cohorts at ${ANS.value_to_cac_trend[0].early_2024_ratio?.toFixed(2)}× CAC. By Dec 2025 the three newest cohorts stood at ${ANS.value_to_cac_trend.at(-1).latest_three_ratio.toFixed(2)}× (${pc(ANS.value_to_cac_trend.at(-1).latest_three_forecast_share)} of that value still forecast), versus ${ANS.value_to_cac_trend.at(-1).early_2024_ratio.toFixed(2)}× for Jan–Mar 2024, now fully observed.`:""}</p>
 <p><b>When did the evidence first support the recommendation?</b> ${ANS.first_month_pattern_matches_report?`Value exceeded iCAC in both build-skill cells and fell short in both save-time cells from <b>${mname(ANS.first_month_pattern_matches_report)}</b>`:"Not within the replay"}${ANS.first_month_pattern_stable_through_dec_2025&&ANS.first_month_pattern_stable_through_dec_2025!=ANS.first_month_pattern_matches_report?`; the pattern held without interruption from <b>${mname(ANS.first_month_pattern_stable_through_dec_2025)}</b>`:ANS.first_month_pattern_stable_through_dec_2025?" and held every month after":""}. The report's <i>priority</i> came later: search / build skill only cleared even its pessimistic (upper) iCAC bound from <b>${mname(ANS.first_month_matching_with_search_build_skill_above_upper_icac)}</b>; in Jul–Nov 2025 partner / build skill showed the larger margin (see the decision table each month). ${ANS.note} Recent-cohort values are about ${pc(ANS.value_to_cac_trend.at(-1).latest_three_forecast_share)} forecast, so the latest gains are the least certain.</p>`;
 $("recon").innerHTML=h}
function go(i){idx=Math.max(0,Math.min(DATA.length-1,i));render()}
$("prev").onclick=()=>go(idx-1);$("next").onclick=()=>go(idx+1);$("first").onclick=()=>go(0);$("last").onclick=()=>go(DATA.length-1);$("slider").oninput=e=>go(+e.target.value);
$("play").onclick=()=>{if(timer){clearInterval(timer);timer=null;$("play").textContent="▶ Play";return}$("play").textContent="⏸ Pause";timer=setInterval(()=>{if(idx>=DATA.length-1){clearInterval(timer);timer=null;$("play").textContent="▶ Play";return}go(idx+1)},1200)};
document.addEventListener("keydown",e=>{if(e.key=="ArrowRight")go(idx+1);if(e.key=="ArrowLeft")go(idx-1)});
$("theme").onclick=()=>{const r=document.documentElement,dark=r.dataset.theme?r.dataset.theme=="dark":matchMedia("(prefers-color-scheme: dark)").matches;r.dataset.theme=dark?"light":"dark";render()};
const q=new URLSearchParams(location.search).get("month");go(q?Math.max(0,DATA.findIndex(d=>d.month==q)):0);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", type=Path, default=DEFAULT_LAB)
    ap.add_argument("--out", type=Path, default=HERE / "output")
    a = ap.parse_args()
    run = a.lab / "outputs" / "student"
    payload, recon, answers = build(a.lab, run, a.out / "refits")
    (a.out / "checks").mkdir(parents=True, exist_ok=True)
    (a.out / "replay_data.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    (a.out / "checks" / "reconciliation.json").write_text(json.dumps(recon, indent=2) + "\n", encoding="utf-8")
    (a.out / "checks" / "faq4_answers.json").write_text(json.dumps(answers, indent=2) + "\n", encoding="utf-8")
    html = (HTML.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                .replace("__RECON__", json.dumps(recon, separators=(",", ":")))
                .replace("__ANS__", json.dumps(answers, separators=(",", ":"))))
    (a.out / "studio-north-monthly-replay.html").write_text(html, encoding="utf-8")
    missing = [p["month"] for p in payload if p["model"]["status"] == "missing"]
    print(json.dumps({"months": len(payload), "refits_missing": missing, "reconciliation": recon.get("matches_report"),
                      "first_match": answers["first_month_pattern_matches_report"],
                      "stable_from": answers["first_month_pattern_stable_through_dec_2025"]}, indent=1))


if __name__ == "__main__":
    main()
