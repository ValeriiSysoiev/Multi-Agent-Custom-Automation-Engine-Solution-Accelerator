import base64
import json
import logging
from typing import List, MutableMapping


def get_authenticated_user_details(request_headers):
    user_object = {}

    principal_id_header = request_headers.get("x-ms-client-principal-id")
    principal_id_normalized = (principal_id_header or "").strip().lower()
    # EasyAuth may populate a zero GUID when authentication is disabled or anonymous
    missing_principal = not principal_id_normalized or principal_id_normalized in {
        "00000000-0000-0000-0000-000000000000",
        "anonymous",
    }

    if missing_principal:
        logging.info("No user principal found in headers or principal is anonymous")
        # assume development mode and return the default sample user
        from . import sample_user

        raw_user_object = sample_user.sample_user
    else:
        # if it is, get the user details from the EasyAuth headers
        raw_user_object = {k: v for k, v in request_headers.items()}

    normalized_headers = {k.lower(): v for k, v in raw_user_object.items()}
    user_object["user_principal_id"] = normalized_headers.get(
        "x-ms-client-principal-id"
    )
    user_object["user_name"] = normalized_headers.get("x-ms-client-principal-name")
    user_object["auth_provider"] = normalized_headers.get("x-ms-client-principal-idp")
    user_object["auth_token"] = normalized_headers.get("x-ms-token-aad-id-token")
    user_object["client_principal_b64"] = normalized_headers.get(
        "x-ms-client-principal"
    )
    user_object["aad_id_token"] = normalized_headers.get("x-ms-token-aad-id-token")

    client_principal_b64 = user_object.get("client_principal_b64")
    payload = {}
    if client_principal_b64:
        try:
            decoded = base64.b64decode(client_principal_b64)
            payload = json.loads(decoded.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive parsing
            logging.exception("Failed to decode client principal: %s", exc)
            payload = {}

    user_roles = payload.get("userRoles") if isinstance(payload, dict) else None
    if isinstance(user_roles, list):
        user_object["user_roles"] = user_roles
    else:
        user_object["user_roles"] = []

    # Some EasyAuth configurations omit x-ms-client-principal but still provide
    # x-ms-client-principal-roles as a JSON or CSV payload; hydrate roles if present.
    if not user_object["user_roles"]:
        raw_roles = normalized_headers.get("x-ms-client-principal-roles")
        if raw_roles:
            try:
                parsed = json.loads(raw_roles)
                if isinstance(parsed, list):
                    user_object["user_roles"] = [str(role) for role in parsed if role]
            except json.JSONDecodeError:
                # fall back to comma/semicolon separated roles
                candidates = [role.strip() for role in raw_roles.split(",") if role.strip()]
                if candidates:
                    user_object["user_roles"] = candidates

    claims = payload.get("claims") if isinstance(payload, dict) else None
    normalized_claims: MutableMapping[str, List[str]] = {}
    groups: List[str] = []
    applications: List[str] = []

    if isinstance(claims, list):
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_type = str(claim.get("typ", "")).lower()
            value = claim.get("val")
            if value is None:
                continue
            normalized_claims.setdefault(claim_type, []).append(str(value))
            if claim_type in {"groups", "group"}:
                groups.append(str(value))
            if claim_type in {"app", "application", "appname", "appid"}:
                applications.append(str(value))

    user_object["claims"] = normalized_claims
    user_object["groups"] = groups
    user_object["applications"] = applications

    return user_object


def get_tenantid(client_principal_b64):
    logger = logging.getLogger(__name__)
    tenant_id = ""
    if client_principal_b64:
        try:
            # Decode the base64 header to get the JSON string
            decoded_bytes = base64.b64decode(client_principal_b64)
            decoded_string = decoded_bytes.decode("utf-8")
            # Convert the JSON string1into a Python dictionary
            user_info = json.loads(decoded_string)
            # Extract the tenant ID
            tenant_id = user_info.get("tid")  # 'tid' typically holds the tenant ID
        except Exception as ex:
            logger.exception(ex)
    return tenant_id
