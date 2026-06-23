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
    "learnings": ("What we are learning as the model runs: which flags proved "
                  "right, reviewer notes, and the reasons behind every change."),
    "audit": ("The tamper-evident record of everything the system did and who "
              "told it to. Read-only here; exportable for an auditor."),
    "models": ("The model registry. Which version is live, its back-tested "
               "metrics, and the governed path to promote a new one."),
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
}


def purpose(screen: str) -> str:
    return SCREENS.get(screen, "")


def verify_coverage() -> Dict[str, bool]:
    """Used by the help-coverage test: every screen must have a purpose."""
    return {k: bool(v and v.strip()) for k, v in SCREENS.items()}
