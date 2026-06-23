"""The MIA3 data contract — the canonical schema for the monthly input file.

This is the single source of truth for "what columns the engine expects".
It is derived from the EWS deck's named feature set and the MicroFlex
conventions, per the Build Plan. The real back-tested model's feature list
drops in by editing MODEL_FEATURES below (and shipping the artifact); nothing
else needs to change.

Three groups of columns:
  * IDENTITY  — who the account is and how it rolls up (FI / scheme / sector).
  * RISKSCORE — the two business inputs to the 50/30/20 risk score that are
                NOT model features: Exposure at Default and Outstanding Ratio.
                (The third input, probability of MIA3 slip, is the model's
                output, not a column.)
  * MODEL     — the features the trained model consumes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class Column:
    name: str
    dtype: str  # "str" | "float" | "int"
    required: bool
    description: str
    # How a missing value is handled at validation/scoring time.
    #   "reject"  -> the row is quarantined (cannot be scored safely)
    #   "default" -> filled with `default`, confidence is reduced
    on_missing: str = "reject"
    default: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None


# --- Identity / roll-up columns -------------------------------------------
IDENTITY_COLUMNS: List[Column] = [
    Column("account_id", "str", True, "Unique account / application number."),
    Column("fi_id", "str", True, "Financial institution code (row-level access key)."),
    Column("fi_name", "str", False, "Financial institution display name.", on_missing="default", default=None),
    Column("scheme", "str", True, "Guarantee scheme code."),
    Column("sector", "str", True, "Economic sector."),
    Column("branch", "str", False, "Originating CGC branch.", on_missing="default", default=None),
    Column("as_of_date", "str", False, "Snapshot date of the record (YYYY-MM-DD).", on_missing="default", default=None),
]

# --- Risk-score inputs (not model features) -------------------------------
RISKSCORE_COLUMNS: List[Column] = [
    Column("ead", "float", True,
           "Exposure at Default in RM — amount CGC stands to lose on default.",
           minimum=0.0),
    Column("outstanding_ratio", "float", True,
           "Outstanding / utilisation ratio (0-1). Customer leverage indicator.",
           minimum=0.0, maximum=1.5),
]

# --- Model features --------------------------------------------------------
# NOTE: replacing the synthetic model with the real back-tested artifact means
# aligning this list with the artifact's feature_names_in_. The loader checks
# the two agree and refuses to score on a mismatch.
MODEL_FEATURES: List[Column] = [
    # Repayment behaviour
    Column("mia", "int", True, "Months in arrears at snapshot (0-2; 3+ is the event).",
           minimum=0, maximum=2),
    Column("prev_delinquency_count", "int", True, "Count of prior delinquency episodes (12m).",
           on_missing="default", default=0, minimum=0),
    Column("arrears_movement_trend", "int", True,
           "Direction of arrears over last 3 snapshots: -1 improving, 0 flat, 1 worsening.",
           on_missing="default", default=0, minimum=-1, maximum=1),
    Column("payment_consistency", "float", True,
           "Share of scheduled payments made on time (0-1).",
           on_missing="default", default=0.5, minimum=0.0, maximum=1.0),
    # Financial strength
    Column("cost_to_income_ratio", "float", True, "Cost-to-income ratio.",
           on_missing="default", default=0.7, minimum=0.0),
    Column("profit_margin", "float", True, "Net profit margin (can be negative).",
           on_missing="default", default=0.05),
    # Business stability
    Column("length_of_business_months", "int", True, "Age of business in months.",
           on_missing="default", default=36, minimum=0),
    # Exposure indicators
    Column("outstanding_amount", "float", True, "Current outstanding financing (RM).",
           minimum=0.0),
    Column("utilization_ratio", "float", True, "Drawn / approved limit (0-1).",
           on_missing="default", default=0.5, minimum=0.0, maximum=2.0),
    # Engineered features proven in the deck
    Column("debt_pressure_to_remaining", "float", True,
           "Debt-service pressure relative to remaining tenor/headroom.",
           on_missing="default", default=0.5, minimum=0.0),
    Column("repayment_stress_ratio", "float", True,
           "Repayment obligation vs. capacity (higher = more stress).",
           on_missing="default", default=0.5, minimum=0.0),
    Column("payment_gap_x_pd", "float", True,
           "Interaction: payment gap magnitude x baseline PD.",
           on_missing="default", default=0.1, minimum=0.0),
]

ALL_COLUMNS: List[Column] = IDENTITY_COLUMNS + RISKSCORE_COLUMNS + MODEL_FEATURES
COLUMN_BY_NAME: Dict[str, Column] = {c.name: c for c in ALL_COLUMNS}

MODEL_FEATURE_NAMES: List[str] = [c.name for c in MODEL_FEATURES]
REQUIRED_COLUMNS: List[str] = [c.name for c in ALL_COLUMNS if c.required]
# Columns whose absence cannot be defaulted away — the row must be quarantined.
HARD_REQUIRED: List[str] = [c.name for c in ALL_COLUMNS if c.required and c.on_missing == "reject"]

# The binary training/outcome label (present only in training & learnings data).
LABEL_COLUMN = "mia3_event"


def coerce(column: Column, value):
    """Coerce a raw cell to the column's declared type; raise on impossible."""
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return None
    if column.dtype == "str":
        s = str(value).strip()
        return s if s != "" else None
    if column.dtype == "int":
        return int(round(float(value)))
    return float(value)


def contract_as_dict() -> dict:
    """Machine-readable contract, used by the docs endpoint and tests."""
    def grp(cols: List[Column]) -> list:
        return [
            {
                "name": c.name, "type": c.dtype, "required": c.required,
                "on_missing": c.on_missing, "default": c.default,
                "min": c.minimum, "max": c.maximum, "description": c.description,
            }
            for c in cols
        ]

    return {
        "identity": grp(IDENTITY_COLUMNS),
        "risk_score_inputs": grp(RISKSCORE_COLUMNS),
        "model_features": grp(MODEL_FEATURES),
        "label_column": LABEL_COLUMN,
    }
