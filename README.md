# Studio North: month-by-month replay dashboard

A self-contained browser dashboard that replays the Studio North customer-economics report one month at a time, from January 2024 to December 2025. Each **as-of month** shows only what Studio North could have known by the end of that month:

- the observed retention triangle
- each joining cohort's mix across the four channel × need segments
- company revenue, contribution and acquisition spend
- each cohort's 12-receipt contribution LTV, historical average CAC and payback
- holdout-based iCAC, from tests completed by that date
- the value-versus-iCAC acquisition decision

Observed results are drawn solid. Forecasts are hatched and dashed, and come from the report's own model **refitted at every as-of month on records dated through that month only**.

This implements prompt 4 of the course's *"What else to prompt after running the skill"* FAQ. It is an extension of a completed guided run of the [customer-economics lab](https://github.com/longxiutian/customer-economics-lab) at commit `0e40ce3cd0b788a3914ca4eb9f90d58ae1b62903`. The lab's data, SQL, model code and PDF are reused unchanged; nothing is regenerated.

**Open the dashboard:** download [`output/studio-north-monthly-replay.html`](output/studio-north-monthly-replay.html) and open it in any browser. It works offline and needs no install.

**Controls:** ◀ Prev / Next ▶ (or the arrow keys), the slider, ⏮ / ⏭ for the first and last month, ▶ Play to advance automatically, and ◐ to toggle dark mode. Hover any bar or cell for exact values. Each chart has a table view. Add `?month=2025-07` to the URL to open a given month.

**Demo video:** [`demo/studio-north-replay-demo.webm`](demo/studio-north-replay-demo.webm) (about 2½ minutes, captioned, no audio).

## How each as-of month is built

| Evidence | Source in the lab run | Rule for as-of month M |
|---|---|---|
| Retention, revenue, contribution, cash after CAC | `tables/cohort_totals.csv`, `cohort_age_summary.csv`, `cohort_cash_economics.csv`, `company_totals.csv` (outputs of the lab's `sql/01_views.sql`) | Rows with `calendar_month ≤ M`. Cohorts that hadn't joined are hidden. Observed payback is the first age whose cumulative balance is ≥ 0 inside the cut. |
| Cohort mix | `cohort_age_summary.csv`, age 0 | Cohorts joined by M |
| Historical average CAC | targeted spend in the cohort month ÷ customers acquired | Known at the end of the cohort's month |
| iCAC | `tables/channel_cac.csv` (holdout tests) | Only tests whose 31-day window ended by the first instant after M; the latest per cell is "current". The first wave completes at the end of July 2025. |
| Forecast LTV and payback | `asof_refit.py` → `output/refits/M.json` | The report's hierarchical shifted-Beta-Geometric + Gamma model (`cohort_lab.model._posterior`), refitted on cells dated ≤ M with the report's seed (20261116), 4 × (1,000 + 1,000) NUTS draws and the same gates (R-hat ≤ 1.01, ESS ≥ 400, 0 divergences). Gross-to-contribution ratios use training cells only. No parameter fitted on later data is reused. |

Jan and Feb 2024 have too little renewal history for the model (it needs at least 12 renewal cells), so their forecasts are left blank and the dashboard says so. A month that failed the gates would also be left blank; none did.

Definitions follow the report:
- **Cohort:** the month of a customer's first successful payment. Age 0 is the acquisition month.
- **Retention:** paid subscription periods ÷ the original acquired customers.
- **Contribution:** net revenue (after discounts and refunds) − variable costs.
- **LTV:** 12 monthly receipts of contribution, discounted 1% per month (t = age + 1), before CAC.
- **Net value:** LTV − historical average CAC, subtracted once.
- **Payback:** the first month in which cumulative undiscounted contribution ≥ CAC.

The decision panel pairs current iCAC with the value before CAC of the latest cohort that has six observed receipts in every tested cell. It assumes additional customers are worth that cohort's average; this is a planning projection, not experimentally measured lifetime value. Forecast bands show parameter uncertainty only.

## Checks

- `output/checks/reconciliation.json`: the Dec 2025 replay compared with the original report tables (`cohort_valuation.csv`, `channel_value_decision.csv`) behind the PDF.
- `output/checks/cutoff-rebuild-*.json`: FAQ 4's follow-up check. `verify_cutoff.py` truncates the eight raw CSVs to records dated before the cutoff, reruns the lab's canonical SQL with `data_as_of` = cutoff, and confirms the rebuilt tables equal the dashboard's filtered view.
- `output/checks/faq4_answers.json`: answers to FAQ 4's two questions, computed from the replay.
- `output/checks/screen-*.png`: rendered screenshots used for visual review.

## Reproduce

These scripts use the lab's locked `uv` environment, so place this folder next to the extracted lab (`../customer-economics-lab`) after completing a guided run.

```bash
uv run --frozen --project ../customer-economics-lab python asof_refit.py          # 24 as-of refits (~1 min each on CPU; resumable)
uv run --frozen --project ../customer-economics-lab python verify_cutoff.py --as-of 2025-03
uv run --frozen --project ../customer-economics-lab python verify_cutoff.py --as-of 2025-09
uv run --frozen --project ../customer-economics-lab python build_dashboard.py
node screenshot.mjs 2024-03 2025-07 2025-12                                        # optional visual QA
node record_demo.mjs                                                               # optional: re-record the demo video
```

The data are the lab's original synthetic records (dataset 5.1), not private course data. Fixed operating costs and the causal long-run value of advertising are outside what these exports establish.
