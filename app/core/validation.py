"""Input validation and the data-quality report.

The engine confirms an incoming file matches the data contract BEFORE it
scores anything. Rows that cannot be scored safely are quarantined, never
silently guessed. Rows with a defaultable gap are filled and flagged so
their confidence can be reduced downstream.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.core import features as F


@dataclass
class RowIssue:
    account_id: Optional[str]
    column: str
    problem: str  # "missing_required" | "out_of_range" | "bad_type" | "defaulted"
    detail: str


@dataclass
class ValidationResult:
    accepted: pd.DataFrame
    quarantined: pd.DataFrame
    issues: List[RowIssue] = field(default_factory=list)
    missing_columns: List[str] = field(default_factory=list)

    @property
    def n_accepted(self) -> int:
        return len(self.accepted)

    @property
    def n_quarantined(self) -> int:
        return len(self.quarantined)

    @property
    def defaulted_count(self) -> int:
        return sum(1 for i in self.issues if i.problem == "defaulted")

    def quality_report(self) -> Dict[str, object]:
        by_problem: Dict[str, int] = {}
        for i in self.issues:
            by_problem[i.problem] = by_problem.get(i.problem, 0) + 1
        total = self.n_accepted + self.n_quarantined
        return {
            "rows_in": total,
            "rows_accepted": self.n_accepted,
            "rows_quarantined": self.n_quarantined,
            "rows_defaulted": self.defaulted_count,
            "missing_columns": self.missing_columns,
            "issues_by_type": by_problem,
            "acceptance_rate": round(self.n_accepted / total, 4) if total else 0.0,
        }


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """Read a CSV or JSON upload into a DataFrame."""
    name = (filename or "").lower()
    if name.endswith(".json") or content.strip()[:1] in (b"[", b"{"):
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, dict) and "accounts" in data:
            data = data["accounts"]
        return pd.DataFrame(data)
    return pd.read_csv(io.BytesIO(content))


def validate(df: pd.DataFrame) -> ValidationResult:
    """Validate a portfolio frame against the contract."""
    df = df.copy()
    issues: List[RowIssue] = []

    # 1. Structural check — are the hard-required columns present at all?
    present = set(df.columns)
    missing_cols = [c for c in F.HARD_REQUIRED if c not in present]
    if missing_cols:
        # No row can be scored; the whole file is quarantined structurally.
        return ValidationResult(
            accepted=df.iloc[0:0], quarantined=df,
            issues=[RowIssue(None, c, "missing_required",
                             f"Required column '{c}' is absent from the file.")
                    for c in missing_cols],
            missing_columns=missing_cols,
        )

    # Ensure every contract column exists so downstream code can rely on it.
    for col in F.ALL_COLUMNS:
        if col.name not in df.columns:
            df[col.name] = None

    accept_mask = pd.Series(True, index=df.index)

    for idx, row in df.iterrows():
        acc_id = row.get("account_id")
        for col in F.ALL_COLUMNS:
            raw = row.get(col.name)
            try:
                value = F.coerce(col, raw)
            except (ValueError, TypeError):
                if col.required and col.on_missing == "reject":
                    accept_mask.at[idx] = False
                    issues.append(RowIssue(acc_id, col.name, "bad_type",
                                           f"Cannot read '{raw!r}' as {col.dtype}."))
                    continue
                value = None

            if value is None:
                if col.on_missing == "reject" and col.required:
                    accept_mask.at[idx] = False
                    issues.append(RowIssue(acc_id, col.name, "missing_required",
                                           "Required value is missing; row quarantined."))
                elif col.default is not None:
                    df.at[idx, col.name] = col.default
                    issues.append(RowIssue(acc_id, col.name, "defaulted",
                                           f"Missing; filled with default {col.default}."))
                continue

            # Range checks for numerics.
            if col.dtype in {"int", "float"}:
                if col.minimum is not None and value < col.minimum:
                    accept_mask.at[idx] = False
                    issues.append(RowIssue(acc_id, col.name, "out_of_range",
                                           f"{value} < min {col.minimum}."))
                    continue
                if col.maximum is not None and value > col.maximum:
                    accept_mask.at[idx] = False
                    issues.append(RowIssue(acc_id, col.name, "out_of_range",
                                           f"{value} > max {col.maximum}."))
                    continue
            df.at[idx, col.name] = value

    accepted = df[accept_mask].copy()
    quarantined = df[~accept_mask].copy()
    return ValidationResult(accepted=accepted, quarantined=quarantined,
                            issues=issues, missing_columns=[])
