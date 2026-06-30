"""The read-only viewer role: can view staff screens, cannot mutate anything."""
import pytest
from fastapi import HTTPException

from app.auth.deps import require_internal, require_staff_view, require_writer
from app.db.models import User


def _u(role):
    return User(username=role, role=role, display_name=role, password_hash="x")


def test_viewer_can_view_staff_screens():
    assert require_staff_view(_u("viewer")).role == "viewer"
    assert require_staff_view(_u("internal")).role == "internal"


def test_viewer_cannot_change_governed_settings():
    with pytest.raises(HTTPException):
        require_internal(_u("viewer"))
    # branch and fi also can't reach governance
    with pytest.raises(HTTPException):
        require_internal(_u("branch"))


def test_viewer_cannot_make_operational_writes():
    with pytest.raises(HTTPException):
        require_writer(_u("viewer"))
    # internal / branch / fi can write
    for role in ("internal", "branch", "fi"):
        assert require_writer(_u(role)).role == role


def test_viewer_is_seeded():
    from app.services.seed import DEFAULT_USERS
    assert any(u[0] == "viewer" and u[2] == "viewer" for u in DEFAULT_USERS)
