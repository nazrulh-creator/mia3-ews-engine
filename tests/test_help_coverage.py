"""Build-time help check (adopted from MicroFlex): every screen has a purpose.

Mirrors MicroFlex's rule that the build fails if any screen lacks help text.
"""
from app import web_help


def test_every_screen_has_a_purpose():
    coverage = web_help.verify_coverage()
    missing = [k for k, ok in coverage.items() if not ok]
    assert not missing, f"Screens missing purpose text: {missing}"


def test_known_screens_registered():
    # The screens the routers render must all be in the help registry.
    expected = {"dashboard", "accounts", "account_detail", "review", "runs",
                "tuning", "demo", "learnings", "audit", "models", "contract", "login"}
    assert expected.issubset(set(web_help.SCREENS))
