"""
Tests for the admin authorization classification (app/auth.py + app/admin.py).

Auth/authz is future scope, so `require_admin` is intentionally permissive today.
These tests pin two things:
  1. Every admin route is *classified* admin-only (depends on `require_admin`),
     so RBAC can later be enforced in exactly one place.
  2. The current gate is open (no 401/403), preserving today's behavior.
"""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import require_admin


def test_require_admin_is_open_today():
    """The dependency currently allows the request through (no exception)."""
    app = FastAPI()

    @app.get("/guarded", dependencies=[Depends(require_admin)])
    def guarded():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/guarded")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_admin_router_is_classified_admin():
    """admin_router must carry require_admin as a router-level dependency."""
    admin = pytest.importorskip("app.admin")  # skip if optional deps unavailable
    dep_calls = [d.dependency for d in admin.admin_router.dependencies]
    assert require_admin in dep_calls, "admin_router is not classified admin-only"
