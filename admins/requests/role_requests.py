from base.services.base_service import Validator, ServiceResponse
from base.helpers.auth_helpers import _parse_body


def _fail(errors: str) -> tuple:
    return None, ServiceResponse.error(errors)


def _ok(data: dict) -> tuple:
    return data, None


def create_role_request(request) -> tuple:
    body = _parse_body(request)

    name = str(body.get("name", ""))
    slug = str(body.get("slug", ""))
    description = str(body.get("description", ""))

    v = Validator()
    v.required(name, "Name").max_length(name, 50, "Name")
    v.required(slug, "Slug").max_length(slug, 50, "Slug")

    if not v.is_valid:
        return _fail(v.errors)

    return _ok({
        "name": name.strip(),
        "slug": slug.strip().lower(),
        "description": description.strip(),
    })


def update_role_request(request) -> tuple:
    body = _parse_body(request)

    name = str(body["name"]) if "name" in body else None
    slug = str(body["slug"]) if "slug" in body else None
    description = str(body["description"]) if "description" in body else None

    v = Validator()
    if name is not None:
        v.required(name, "Name").max_length(name, 50, "Name")
    if slug is not None:
        v.required(slug, "Slug").max_length(slug, 50, "Slug")

    if not v.is_valid:
        return _fail(v.errors)

    data = {}
    if name is not None:
        data["name"] = name.strip()
    if slug is not None:
        data["slug"] = slug.strip().lower()
    if description is not None:
        data["description"] = description.strip()

    if not data:
        return _fail("No fields to update")

    return _ok(data)


def assign_permission_request(request) -> tuple:
    body = _parse_body(request)
    permission_id = body.get("permission_id")

    v = Validator()
    v.required(permission_id, "permission_id")

    if not v.is_valid:
        return _fail(v.errors)

    try:
        return _ok({"permission_id": int(permission_id)})
    except (ValueError, TypeError):
        return _fail("Invalid permission_id")


def remove_permission_request(request) -> tuple:
    body = _parse_body(request)
    permission_id = body.get("permission_id")

    v = Validator()
    v.required(permission_id, "permission_id")

    if not v.is_valid:
        return _fail(v.errors)

    try:
        return _ok({"permission_id": int(permission_id)})
    except (ValueError, TypeError):
        return _fail("Invalid permission_id")


def bulk_assign_permissions_request(request) -> tuple:
    body = _parse_body(request)
    permission_ids = body.get("permission_ids", [])

    if not isinstance(permission_ids, list) or not permission_ids:
        return _fail("permission_ids must be a non-empty list")

    try:
        permission_ids = [int(pid) for pid in permission_ids]
    except (ValueError, TypeError):
        return _fail("All permission_ids must be integers")

    return _ok({"permission_ids": permission_ids})
