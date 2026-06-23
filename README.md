# MIA3 Early Warning Engine

A standalone portfolio-monitoring platform that turns the back-tested **MIA3
predictor model** into a working tool for CGC's FI partners, branches, and the
internal risk team. Built by **Strategic Data Analytics (SDA)**, a team within
CGC Malaysia. It reuses the proven **MicroFlex** governance patterns rather than
reinventing them.

> **MicroFlex is a gatekeeper** — it decides whether to let a new loan through the
> door. **MIA3 is a smoke detector** — it watches the loans already inside and
> raises an alarm when one starts to smoulder.

The app carries SDA team ownership marks, **not** CGC corporate branding.

## What it does

1. **Scores** the whole guaranteed portfolio for the probability of slipping into
   Months-in-Arrears 3 (MIA 3).
2. **Classifies** each account into four risk bands via the deck framework:
   `Risk = 0.5·rank(P(MIA3)) + 0.3·rank(EAD) + 0.2·rank(Outstanding Ratio)`.
3. **Routes** work by confidence — high-confidence high-risk to the worklist,
   borderline cases to mandatory human review.
4. **Explains** every flag (SHAP) and every band (live arithmetic), and produces a
   printable one-page case report.

> ⚠️ **The one caution.** The model favours recall (~0.73) over precision (~0.49):
> roughly half the flags are false alarms. That is fine for prioritising accounts
> for a human to look at, and unacceptable for automated action. **A person stays
> in the loop on every high-risk call.**

## Quick start (local, zero external services)

```bash
cd mia3-ews-engine
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # full stack (XGBoost/SHAP/LIME)
# ...or the lean runtime if you just want to run it:
# pip install fastapi "uvicorn[standard]" jinja2 python-multipart SQLAlchemy \
#   pydantic pandas numpy "passlib[bcrypt]" itsdangerous python-docx Pillow APScheduler

cp .env.example .env
uvicorn app.main:app --reload --port 8080
```

Open <http://localhost:8080>. Sign in (TEST, synthetic data):

| Role | Login | Sees |
|---|---|---|
| Internal Risk | `internal` / `internal123` | Everything + tuning |
| Internal Risk (checker) | `checker` / `checker123` | For dual-control approvals |
| Branch | `branch` / `branch123` | Action worklist + review |
| FI (Maybank) | `fi_mbb` / `fi123` | Only Maybank's book |

Then: **Demo → Generate & score demo portfolio**, and explore the **Dashboard**.

> The engine runs on a **deterministic synthetic stand-in model** when no real
> artifact is present, so it works with or without the heavy ML libraries.

## CLI (Phase 1 milestone — no web, no DB)

```bash
python -m scripts.generate_demo_data                 # writes data/synthetic/*.csv|json
python -m scripts.score_file data/synthetic/demo_portfolio.csv
```

## Dropping in the real model

The synthetic stand-in is a transparent logistic model used only until the
back-tested XGBoost artifact is available. To switch:

```bash
export MIA3_MODEL_PATH=/path/to/mia3_xgb.json   # .json/.ubj or pickled sklearn
```

The loader checks the artifact's features match the data contract
(`app/core/features.py`) and refuses to score on a mismatch. No other code
changes. `python -m scripts.train_synthetic_model` shows the full produce→load path.

## The eight requested features (and where they live)

| # | Feature | Where |
|---|---|---|
| 4.1 | Model explainability (SHAP & LIME) | `app/core/explain.py`, account detail page |
| 4.2 | Demonstration mode | `app/core/synthetic.py`, `/demo` |
| 4.3 | Auditability (hash-chained) | `app/db/audit.py`, `/audit` |
| 4.4 | Decision explainability | account detail "How the band was reached" + case report |
| 4.5 | Visualisation layer | `/dashboard` (by FI/scheme/sector, trend, drill-down) |
| 4.6 | Prediction-radar tuning | `/tuning` (dual control + re-banding preview) |
| 4.7 | Confidence-based review flow | `app/core/confidence.py`, `/review` |
| 4.8 | Learnings library | `/learnings` |

**Adopted from MicroFlex on top:** dual control on every governed change, a
calibration layer, a golden test pack, a portfolio early-warning ladder, a
printable case report, the four-layer help system, guided/compact modes,
universal problem reporting, and the LIVE/TEST split.

## Build sequence (as delivered)

- **Phase 1** Scoring core — `app/core/*`, `scripts/score_file.py`
- **Phase 2** Database & hash-chained audit — `app/db/*`
- **Phase 3** Web layer & three views — `app/routers/*`, `app/templates/*`
- **Phase 4** Explainability & decision transparency
- **Phase 5** Review flow & dual-control tuning
- **Phase 6** Demo mode, learnings, scheduled run, deployment (`Dockerfile`, `fly.toml`)

## Tests & the golden pack

```bash
python -m scripts.build_golden_pack    # freeze expected results (sign off in prod)
pytest                                  # scoring, pipeline, golden pack, audit chain, help coverage
```

## Working safeguards

- Nothing destructive or outbound (deploy to LIVE, dispatch to FIs) without explicit go-ahead.
- Human-in-the-loop on every high-risk call while precision is low.
- Thresholds/weights are governed, logged settings — never edited in source.
- No real borrower data in external AI tools — synthetic/de-identified only.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the coupling rules and the
safe-degradation table.
