from base.services.base_service import Validator, ServiceResponse
from base.helpers.auth_helpers import _parse_body
from base.models import Facility


def _fail(errors: str) -> tuple:
    return None, ServiceResponse.error(errors)


def _ok(data: dict) -> tuple:
    return data, None


VALID_FACILITY_TYPES = [c[0] for c in Facility.Type.choices]


def create_facility_request(request) -> tuple:
    body = _parse_body(request)

    code = str(body.get("code", "")).strip()
    name = str(body.get("name", "")).strip()

    v = Validator()
    v.required(code, "Code").max_length(code, 50, "Code")

    if not v.is_valid:
        return _fail(v.errors)

    data = {
        "code": code,
        "name": name,
        "address": str(body.get("address", "")).strip(),
        "city": str(body.get("city", "")).strip(),
        "state": str(body.get("state", "")).strip(),
        "zip_code": str(body.get("zip_code", "")).strip(),
    }

    facility_type = str(body.get("facility_type", "warehouse")).strip()
    if facility_type not in VALID_FACILITY_TYPES:
        return _fail(f"Invalid facility_type. Must be one of: {', '.join(VALID_FACILITY_TYPES)}")
    data["facility_type"] = facility_type

    return _ok(data)


def update_facility_request(request) -> tuple:
    body = _parse_body(request)

    allowed_fields = {"code", "name", "address", "city", "state", "zip_code", "facility_type"}
    data = {}

    for field in allowed_fields:
        if field in body:
            data[field] = str(body[field]).strip()

    if not data:
        return _fail("No fields to update")

    if "code" in data:
        v = Validator()
        v.max_length(data["code"], 50, "Code")
        if not v.is_valid:
            return _fail(v.errors)

    if "facility_type" in data and data["facility_type"] not in VALID_FACILITY_TYPES:
        return _fail(f"Invalid facility_type. Must be one of: {', '.join(VALID_FACILITY_TYPES)}")

    return _ok(data)


def list_facilities_request(request) -> tuple:
    page = request.GET.get("page", "1")
    per_page = request.GET.get("per_page", "20")

    try:
        page = max(1, int(page))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = min(100, max(1, int(per_page)))
    except (ValueError, TypeError):
        per_page = 20

    return _ok({
        "page": page,
        "per_page": per_page,
        "facility_type": request.GET.get("facility_type", "").strip(),
        "state": request.GET.get("state", "").strip(),
        "city": request.GET.get("city", "").strip(),
        "search": request.GET.get("search", "").strip(),
    })
