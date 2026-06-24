"""
Authentication / authorization hooks.

NOTE: This application does not yet implement authentication or authorization;
that is planned future scope. This module exists so that every admin-only route
is already *classified* as admin (it depends on `require_admin`), giving us a
single, well-known place to enforce role-based access control (RBAC) later.

Today `require_admin` is intentionally permissive (it allows every request).
When RBAC lands, implement the real check here (validate the bearer token /
session, look up the caller's role, and raise `HTTPException(403)` for
non-admins). No route code needs to change — only this function.
"""
from fastapi import Request

from . import logger


async def require_admin(request: Request) -> None:
    """Future RBAC injection point for admin-only endpoints.

    Currently a no-op gate (open access) because auth/authz is not yet built.
    Keeping it as a dependency means all admin routes are tagged admin-gated and
    enforcement can be switched on in exactly one place.
    """
    # TODO(rbac): replace with real role verification once auth is implemented, e.g.
    #   user = await get_current_user(request)
    #   if not user or not user.is_admin:
    #       raise HTTPException(status_code=403, detail="Admin privileges required")
    logger.debug("require_admin: open access (RBAC not yet implemented) for %s", request.url.path)
    return None
