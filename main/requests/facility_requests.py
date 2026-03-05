from base.services.base_service import ServiceResponse


def _fail(errors: str) -> tuple:
    return None, ServiceResponse.error(errors)


def _ok(data: dict) -> tuple:
    return data, None


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
