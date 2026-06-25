"""The four-layer 'teach as you go' help system (adopted from MicroFlex).

Every screen carries a plain-language purpose banner, and fields carry info
text. SCREENS is the registry the templates read, and the test suite enforces
that every registered screen has a purpose — the build-time help check.
"""
from __future__ import annotations

from typing import Dict

# screen key -> plain-language purpose banner shown at the top of the page.
SCREENS: Dict[str, str] = {
    "dashboard": ("Your portfolio at a glance. Counts by risk band, and the "
                  "by-FI, by-scheme and by-sector breakdowns — the radar view. "
                  "Click any total to drill into the accounts behind it."),
    "accounts": ("Every scored account. Filter by band, FI, scheme or sector, "
                 "sort by risk, and open any account to see why it was flagged."),
    "account_detail": ("One account, explained two ways: why the model scored "
                        "it, and how that combined with exposure and leverage "
                        "into a risk band. Print this as a case report."),
    "worklist": ("Accounts the engine wants a person to look at, ordered by "
                 "priority. Confirm, override with a reason, or escalate."),
    "review": ("The human review queue. Borderline-confidence and high-risk "
               "accounts wait here for a decision before any action follows."),
    "runs": ("Run a scoring cycle and see past runs. Drop a CSV/JSON file, or "
             "trigger a run manually. Each run shows its data-quality report."),
    "tuning": ("Adjust the 50/30/20 weights and band cut-offs, or the model "
               "calibration. Changes preview first, then need a second "
               "approver before they go live — nothing changes silently."),
    "demo": ("A safe, synthetic sandbox that exercises every feature and edge "
             "case. Use it to show the platform without touching real data."),
    "learnings": ("A library of reference materials about the engine — guides, "
                  "key concepts and FAQs — plus the record of what we are learning "
                  "as the model runs (outcomes, reviewer notes, change reasoning)."),
    "audit": ("The tamper-evident record of everything the system did and who "
              "told it to. Read-only here; exportable for an auditor."),
    "models": ("The model registry. Which version is live, its back-tested "
               "metrics, and the governed path to promote a new one."),
    "performance": ("How the model is performing against the go-live goals "
                    "(Recall, AUC, false-negative rate) once realised MIA 3 "
                    "outcomes are recorded — per run and segment."),
    "contract": ("The exact data contract: every column the monthly file must "
                 "contain, its type, and how missing values are handled."),
    "login": "Sign in. Your role decides what you can see and do."
}

# field key -> info-icon help text.
FIELDS: Dict[str, str] = {
    "risk_score": "0.5×P(MIA3) rank + 0.3×EAD rank + 0.2×Outstanding-ratio rank.",
    "band": "Very High >3.5, High 3.0–3.5, Moderate 2.0–3.0, Low <2.0.",
    "confidence": "How much to trust this prediction (0–100): model strength, "
                  "data completeness, data quality, population fit, calibration.",
    "review_status": "How the account was routed: fast-track, needs-review, or "
                     "no-review — based on risk band and confidence.",
    "probability": "The model's estimated probability the account slips into "
                    "Months-in-Arrears 3 within the forecast horizon.",
    "ead": "Exposure at Default — the RM amount CGC stands to lose on default.",
    "outstanding_ratio": "Outstanding / utilisation — a customer-leverage signal.",
    "weights": "Component weights must sum to 1.00.",
    "calibration": "Maps raw model output onto observed reality. Defaults to "
                   "uncalibrated so nothing changes silently.",

    # --- Data-entry fields (tooltips on every screen that takes input) -----
    # Login
    "login_username": "Your account name. Your role (internal / branch / FI) "
                      "decides what you can see and do.",
    "login_password": "Your password. Sessions expire after 8 hours of inactivity.",
    # Runs — file upload
    "upload_file": "The monthly portfolio file in CSV or JSON. It is validated "
                   "against the data contract before any scoring happens; "
                   "malformed rows are quarantined, never guessed.",
    "upload_hold": "Tick to hold the results for sign-off (a checkpoint) instead "
                   "of publishing them straight to the FI and branch views.",
    # Tuning — weights
    "w_pd": "Weight on the Probability-of-MIA3 rank. The three weights must "
            "sum to 1.00. Deck default 0.50.",
    "w_ead": "Weight on the Exposure-at-Default rank. Deck default 0.30.",
    "w_outratio": "Weight on the Outstanding-ratio rank. Deck default 0.20.",
    # Tuning — band cut-offs
    "t_very_high": "Score strictly above this is Very High Risk. Deck default 3.5.",
    "t_high": "Score at or above this (and ≤ Very-High cut-off) is High Risk. "
              "Deck default 3.0.",
    "t_moderate": "Score at or above this (and below High) is Moderate Risk; "
                  "below it is Low Risk. Deck default 2.0.",
    "threshold_note": "Why you are making this change. Stored on the audit trail "
                      "with the before/after values.",
    # Tuning — calibration
    "cal_method": "identity = no change (raw output). linear = a·p + b. "
                  "platt = scale/shift on the log-odds.",
    "cal_a": "Slope/scale parameter for the calibration mapping.",
    "cal_b": "Intercept/shift parameter for the calibration mapping.",
    "cal_note": "The back-testing finding behind this calibration. Audited.",
    # Review decision
    "review_decision": "Confirm the model's call, Override it (treatment only — "
                       "the model's number is unchanged), or Escalate.",
    "review_outcome": "Optional: what actually happened to the account. Feeds the "
                      "learnings evidence base for re-calibration.",
    "review_reason": "Required when you override. Recorded with your decision.",
    # Learnings
    "learning_category": "Reviewer note / pattern, an observed outcome, or a "
                         "model/threshold change with its reasoning.",
    "learning_linked": "Optional account id this learning relates to.",
    "learning_title": "A short, searchable headline for this learning.",
    "learning_body": "The detail — what was learned and why it matters.",
    # Realised-outcome capture
    "outcome_actual": "Did this account actually reach Months-in-Arrears 3? This is "
                      "the label the model's performance is judged against.",
    "outcome_intervention": "Tick if a collection/support action was taken. Outcomes "
                            "with an intervention are influenced by that action, not "
                            "just the borrower — they bias the labels (recorded so "
                            "re-calibration can correct for it).",
    "outcome_exit": "If the account left the book before the horizon (settled, "
                    "restructured, written off, closed) — used to handle censoring.",
    # Universal problem reporting
    "problem_detail": "Describe what went wrong. We auto-capture the screen, your "
                      "user and the time, and link it to the audit trail.",
    # Model registry — register / edit
    "model_segment": "Which portfolio this model scores — Guarantee or Financing. "
                     "One model is active per segment, and accounts are routed to "
                     "their segment's model.",
    "model_name": "A human-readable model name, e.g. 'MIA3 XGBoost'.",
    "model_version": "A unique version string, e.g. '2026-Q2'. Two entries cannot "
                     "share a version.",
    "model_kind": "real = a trained artifact you supply; synthetic = the built-in "
                  "deterministic stand-in (no artifact needed).",
    "model_artifact": "Upload the .json/.ubj/.pkl artifact, or give a server path. "
                      "It is validated against the data contract before activation; "
                      "leave empty for a synthetic entry.",
    "model_auc": "Back-tested AUC (0–1). Optional, shown on the registry.",
    "model_recall": "Back-tested recall (0–1). Optional.",
    "model_precision": "Back-tested precision (0–1). Optional.",
    "model_fn": "Back-tested false-negative rate (0–1). Optional.",
    "model_notes": "Provenance and back-testing notes for this version.",
}

# Which screens take data entry, and which field tooltips each must expose —
# used by the build-time check so no data-entry screen ships without tooltips.
DATA_ENTRY_FIELDS: Dict[str, list] = {
    "login": ["login_username", "login_password"],
    "runs": ["upload_file", "upload_hold"],
    "tuning": ["w_pd", "w_ead", "w_outratio", "t_very_high", "t_high",
               "t_moderate", "threshold_note", "cal_method", "cal_a", "cal_b",
               "cal_note"],
    "account_detail": ["review_decision", "review_outcome", "review_reason",
                       "outcome_actual", "outcome_intervention", "outcome_exit"],
    "learnings": ["learning_category", "learning_linked", "learning_title",
                  "learning_body"],
    "models": ["model_name", "model_version", "model_segment", "model_kind",
               "model_artifact", "model_auc", "model_recall", "model_precision",
               "model_fn", "model_notes"],
}


def purpose(screen: str) -> str:
    return SCREENS.get(screen, "")


def verify_coverage() -> Dict[str, bool]:
    """Used by the help-coverage test: every screen must have a purpose."""
    return {k: bool(v and v.strip()) for k, v in SCREENS.items()}


def verify_data_entry_tooltips() -> Dict[str, list]:
    """Build-time check: every declared data-entry field must have a tooltip.

    Returns {screen: [missing field keys]} — empty values mean full coverage.
    """
    missing: Dict[str, list] = {}
    for screen, keys in DATA_ENTRY_FIELDS.items():
        gaps = [k for k in keys if not FIELDS.get(k, "").strip()]
        if gaps:
            missing[screen] = gaps
    return missing
