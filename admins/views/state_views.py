from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from base.decorators.decorators import require_permission
from base.services.base_service import ServiceResponse
from admins.services.state_service import StateService


def _json(result_tuple):
    data, status = result_tuple
    return JsonResponse(data, status=status)


def _parse_page(request):
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
    return page, per_page


def _parse_bool(value):
    return str(value).strip().lower() in ("true", "1", "yes")


@csrf_exempt
@require_GET
@require_permission("analytics.view")
def list_states(request):
    page, per_page = _parse_page(request)
    search = request.GET.get("search", "").strip()
    period = request.GET.get("period", "all").strip()
    sort_by = request.GET.get("sort_by", "-load_count").strip()
    detail = _parse_bool(request.GET.get("detail", ""))

    if period not in ("weekly", "monthly", "yearly", "all"):
        period = "all"

    if not detail:
        return _json(StateService.list_states(
            page=page, per_page=per_page,
            search=search, period=period, sort_by=sort_by,
        ))

    # detail=true but no state specified → error
    return _json(ServiceResponse.error(
        "Provide a state abbreviation via the URL (e.g., /states/TX) "
        "or use detail=false for the list view"
    ))


@csrf_exempt
@require_GET
@require_permission("analytics.view")
def state_detail(request, abbreviation):
    page, per_page = _parse_page(request)
    search = request.GET.get("search", "").strip()
    period = request.GET.get("period", "all").strip()
    sort_by = request.GET.get("sort_by", "-load_count").strip()
    status = request.GET.get("status", "").strip()
    direction = request.GET.get("direction", "all").strip()
    destination = request.GET.get("destination", "").strip()
    origin = request.GET.get("origin", "").strip()

    if period not in ("weekly", "monthly", "yearly", "all"):
        period = "all"
    if direction not in ("inbound", "outbound", "all"):
        direction = "all"

    return _json(StateService.state_detail(
        abbreviation,
        page=page, per_page=per_page,
        search=search, period=period, sort_by=sort_by,
        status=status, direction=direction,
        destination=destination, origin=origin,
    ))


@csrf_exempt
@require_GET
@require_permission("analytics.view")
def state_analytics(request, abbreviation):
    period = request.GET.get("period", "weekly").strip()
    if period not in ("weekly", "monthly", "yearly"):
        period = "weekly"

    return _json(StateService.state_analytics(abbreviation, period=period))
