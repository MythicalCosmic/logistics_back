from base.services.base_service import Validator, ServiceResponse
from base.helpers.auth_helpers import _parse_body


def _fail(errors: str) -> tuple:
    return None, ServiceResponse.error(errors)


def _ok(data: dict) -> tuple:
    return data, None


def create_user_request(request) -> tuple:
    body = _parse_body(request)

    email = str(body.get("email", ""))
    first_name = str(body.get("first_name", ""))
    last_name = str(body.get("last_name", ""))
    password = str(body.get("password", ""))
    phone = str(body.get("phone", ""))
    role_id = body.get("role_id")

    v = Validator()
    v.required(email, "Email").email(email)
    v.required(first_name, "First name").max_length(first_name, 100, "First name")
    v.required(last_name, "Last name").max_length(last_name, 100, "Last name")
    v.required(password, "Password").password_strength(password)

    if not v.is_valid:
        return _fail(v.errors)

    data = {
        "email": email.strip().lower(),
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "password": password,
        "phone": phone.strip(),
    }

    if role_id is not None:
        try:
            data["role_id"] = int(role_id)
        except (ValueError, TypeError):
            return _fail("Invalid role_id")

    return _ok(data)


def update_user_request(request) -> tuple:
    body = _parse_body(request)

    first_name = str(body["first_name"]) if "first_name" in body else None
    last_name = str(body["last_name"]) if "last_name" in body else None
    email = str(body["email"]) if "email" in body else None
    phone = str(body["phone"]) if "phone" in body else None
    is_active = body.get("is_active")

    v = Validator()
    if email is not None:
        v.required(email, "Email").email(email)
    if first_name is not None:
        v.max_length(first_name, 100, "First name")
    if last_name is not None:
        v.max_length(last_name, 100, "Last name")

    if not v.is_valid:
        return _fail(v.errors)

    data = {}
    if first_name is not None:
        data["first_name"] = first_name.strip()
    if last_name is not None:
        data["last_name"] = last_name.strip()
    if email is not None:
        data["email"] = email.strip().lower()
    if phone is not None:
        data["phone"] = phone.strip()
    if is_active is not None:
        data["is_active"] = bool(is_active)

    if not data:
        return _fail("No fields to update")

    return _ok(data)


def list_users_request(request) -> tuple:
    search = request.GET.get("search", "").strip()
    page = request.GET.get("page", "1")
    per_page = request.GET.get("per_page", "20")
    is_active = request.GET.get("is_active")
    role = request.GET.get("role", "").strip()
    sort_by = request.GET.get("sort_by", "-created_at").strip()

    try:
        page = max(1, int(page))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = min(100, max(1, int(per_page)))
    except (ValueError, TypeError):
        per_page = 20

    data = {
        "page": page,
        "per_page": per_page,
        "search": search,
        "role_slug": role,
        "sort_by": sort_by,
    }

    if is_active is not None:
        data["is_active"] = is_active.lower() in ("true", "1", "yes")

    return _ok(data)


def assign_role_request(request) -> tuple:
    body = _parse_body(request)
    role_id = body.get("role_id")

    v = Validator()
    v.required(role_id, "role_id")

    if not v.is_valid:
        return _fail(v.errors)

    try:
        return _ok({"role_id": int(role_id)})
    except (ValueError, TypeError):
        return _fail("Invalid role_id")


def remove_role_request(request) -> tuple:
    body = _parse_body(request)
    role_id = body.get("role_id")

    v = Validator()
    v.required(role_id, "role_id")

    if not v.is_valid:
        return _fail(v.errors)

    try:
        return _ok({"role_id": int(role_id)})
    except (ValueError, TypeError):
        return _fail("Invalid role_id")


def change_password_request(request) -> tuple:
    body = _parse_body(request)
    new_password = str(body.get("new_password", ""))
    force = body.get("force", False) is True

    v = Validator()
    v.required(new_password, "New password").password_strength(new_password)

    if not v.is_valid:
        return _fail(v.errors)

    return _ok({"new_password": new_password, "force": force})
