from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from base.decorators.decorators import require_permission
from base.services.base_service import ServiceResponse
from main.services.route_service import RouteService


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
@require_permission("loads.view")
def list_states(request):
    loads = _parse_bool(request.GET.get("loads", ""))
    if loads:
        page, per_page = _parse_page(request)
        return _json(RouteService.list_states(loads=True, page=page, per_page=per_page))
    return _json(RouteService.list_states())


@csrf_exempt
@require_GET
@require_permission("loads.view")
def list_routes(request):
    page, per_page = _parse_page(request)
    search = request.GET.get("search", "").strip()
    sort_by = request.GET.get("sort_by", "-load_count").strip()
    loads = _parse_bool(request.GET.get("loads", ""))
    week = request.GET.get("week", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    return _json(RouteService.list_routes(
        page=page, per_page=per_page, search=search,
        sort_by=sort_by, loads=loads,
        week=week or None, date_from=date_from or None,
        date_to=date_to or None,
    ))


@csrf_exempt
@require_GET
@require_permission("loads.view")
def get_route(request, route_id):
    return _json(RouteService.get_route(route_id))


@csrf_exempt
@require_GET
@require_permission("loads.view")
def route_loads(request, route_id):
    page, per_page = _parse_page(request)
    status = request.GET.get("status", "").strip()
    sort_by = request.GET.get("sort_by", "-created_at").strip()
    week = request.GET.get("week", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    min_payout = request.GET.get("min_payout")
    max_payout = request.GET.get("max_payout")

    kwargs = {
        "page": page, "per_page": per_page,
        "status": status, "sort_by": sort_by,
        "week": week or None,
        "date_from": date_from or None,
        "date_to": date_to or None,
    }

    if min_payout:
        try:
            kwargs["min_payout"] = float(min_payout)
        except (ValueError, TypeError):
            return _json(ServiceResponse.error("Invalid min_payout"))
    if max_payout:
        try:
            kwargs["max_payout"] = float(max_payout)
        except (ValueError, TypeError):
            return _json(ServiceResponse.error("Invalid max_payout"))

    return _json(RouteService.route_loads(route_id, **kwargs))


@csrf_exempt
@require_GET
@require_permission("loads.view")
def route_analytics(request, route_id):
    period = request.GET.get("period", "weekly").strip()
    if period not in ("weekly", "monthly", "yearly"):
        period = "weekly"

    return _json(RouteService.route_analytics(route_id, period=period))
