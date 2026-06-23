# MIA3 Early Warning Engine — Architecture

A standalone portfolio-monitoring platform that reuses the proven MicroFlex
patterns. **MicroFlex is a gatekeeper** (decides whether to let a new loan in);
**MIA3 is a smoke detector** (watches loans already on the book and raises an
alarm when one starts to smoulder).

## One scoring core, several doors

```
                 ┌─ file upload (CSV/JSON)  ─┐
   data arrives ─┼─ live DB feed (provisioned)┼─► VALIDATION ─► SCORING CORE ─► PostgreSQL ─┬─ Internal Risk view (all + tuning)
                 └─ manual / scheduled run ──┘    (contract)    (model →            (scores,   ├─ Branch worklist
                                                                 50/30/20 →          audit,    └─ FI view (own book only)
                                                                 confidence →        config)
                                                                 explanation)
```

Build the scoring logic once; put several role-based doors in front of it. All
results land in one database that every view reads from. It is a **modular
monolith** (per MicroFlex's advice), not a cluster of microservices.

## The five coupling rules (governance guardrails, adopted verbatim)

1. The scoring engine reads only approved, active model versions — never a draft.
2. The explainability layer reads the stored decision record, never a recomputation.
3. The audit store is append-only and separate from everyday data.
4. A human override changes the *treatment*, never the model's number.
5. Direct DB edits to models/settings are locked out; all change flows through the governed workflow.

## Layers

| Layer | Modules |
|---|---|
| Scoring core | `app/core/` — `features` (contract), `model` (loader + synthetic stand-in), `scoring` (50/30/20), `validation`, `confidence`, `explain`, `batch` |
| Persistence & governance | `app/db/` (ORM + hash-chained audit), `app/services/` (runs, governance/dual-control, seed, case report) |
| Web | `app/routers/` + `app/templates/` — three role-based views, self-documenting JSON API |
| Entrypoints | `scripts/score_file` (CLI), `scripts/run_batch` (scheduled), `scripts/build_golden_pack`, `scripts/train_synthetic_model` |

## Safe degradation (adapted from MicroFlex 2.9)

A case that cannot be scored correctly, or cannot be recorded, is never decided
automatically.

| Failure | Defined response |
|---|---|
| Monthly file malformed / unreadable | Reject the run; surface the parse error; nothing persisted. |
| Required column absent | Whole file structurally quarantined; run records the missing columns. |
| Required value missing in a row | That row quarantined; the rest score normally. |
| Defaultable value missing | Filled with the documented default; the account's confidence is reduced. |
| Acceptance rate < 75% | Run is held for sign-off (checkpoint), not auto-published. |
| Borderline confidence on an elevated band | Routed to mandatory human review, not actioned. |
| SHAP/XGBoost libraries absent | Fall back to the model's exact contributions; explanations still available. |
| Audit store unreachable | Scoring transaction rolls back; no score without a record. |

## Environments

LIVE (green bar) and TEST (amber bar, watermark, `TEST-` run ids) are ringfenced
with **separate databases and audit chains**. Test data can never reach LIVE.
The default is TEST; LIVE must be set deliberately (`MIA3_ENV=LIVE`).
