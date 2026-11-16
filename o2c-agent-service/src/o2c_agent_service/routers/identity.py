"""Who is calling: identity at ingress (E2A v1.7.4, hub design note MP-05, N3).

In Google Cloud, API Gateway verifies the caller's token (Identity Platform) and hands the
verified claims to the service in X-Apigateway-Api-Userinfo; e2a-adapters reads them and E2A's
ClaimMapIdentityResolver maps them to tenant, user and roles. Configured by environment:

  E2A_IDENTITY_SOURCE          gcp_api_gateway (infra/main.tf sets it); unset = local mode
  E2A_IDENTITY_CLAIM_MAP       JSON claim map (default: the Identity Platform preset,
                               tenant = firebase.tenant, roles = roles)
  E2A_IDENTITY_TRUSTED_ISSUERS JSON list of accepted issuers (optional)

Fail-closed when configured: no verified claims -> 401; another tenant named in X-Tenant-Id, or a
role the credentials do not carry in X-User-Role -> 403. X-User-Role chooses which of the caller's
roles to act in; without it, the first role in the claims.

Local mode (no source: tests, local runs, the landscape demo) takes X-Tenant-Id, X-User-Id and
X-User-Role as given, as before.
"""
import os
from dataclasses import dataclass

from e2a import IdentityRefused
from fastapi import Header, HTTPException, Request


@dataclass(frozen=True)
class Caller:
    tenant_id: str
    user_id: str
    role: str


def _config() -> dict:
    from e2a_adapters.identity import preset
    return {"identity_source": os.getenv("E2A_IDENTITY_SOURCE") or None,
            **({} if os.getenv("E2A_IDENTITY_CLAIM_MAP") else {"identity_claim_map": preset("identity_platform")})}


def caller(request: Request, x_tenant_id: str = Header(""), x_user_id: str = Header(""),
           x_user_role: str = Header("")) -> Caller:
    from e2a_adapters.ingress import identity_at_ingress
    try:
        identity = identity_at_ingress(_config(), headers=request.headers, request_tenant=x_tenant_id or None)
    except IdentityRefused as refused:
        status = 401 if "not verified" in str(refused) else 403
        raise HTTPException(status_code=status, detail=str(refused))
    except ValueError as malformed:
        raise HTTPException(status_code=401, detail=str(malformed))
    if identity is None:                                      # local mode
        return Caller(x_tenant_id, x_user_id, x_user_role)
    if x_user_role and x_user_role not in identity.roles:
        raise HTTPException(status_code=403, detail=f"the credentials do not carry the role {x_user_role!r}")
    role = x_user_role or (identity.roles[0] if identity.roles else "")
    return Caller(identity.tenant_id, identity.subject or "", role)
