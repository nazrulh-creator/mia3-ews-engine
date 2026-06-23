"""Golden test pack — the engine must reproduce frozen results exactly.

If this fails, scoring behaviour has changed. Either it is a regression (fix
the code) or an intended change (re-run scripts.build_golden_pack and have the
new pack signed off). Never edit golden_pack.json to make the test pass blindly.
"""
import json
from pathlib import Path

import pytest

GOLDEN = Path(__file__).parent / "golden" / "golden_pack.json"


@pytest.mark.skipif(not GOLDEN.exists(), reason="golden pack not built yet")
def test_golden_pack_reproduces():
    from scripts.build_golden_pack import build
    frozen = json.loads(GOLDEN.read_text())
    fresh = build()
    fz = {c["account_id"]: c for c in frozen["cases"]}
    fr = {c["account_id"]: c for c in fresh["cases"]}
    assert set(fz) == set(fr)
    for acc, exp in fz.items():
        got = fr[acc]
        assert abs(got["probability"] - exp["probability"]) < 1e-6, acc
        for key in ["pd_rank", "ead_rank", "outratio_rank", "risk_score",
                    "band", "confidence", "confidence_band", "review_status"]:
            assert got[key] == exp[key], f"{acc}.{key}: {got[key]} != {exp[key]}"
