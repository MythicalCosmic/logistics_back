from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from base.decorators.decorators import require_permission
from admins.services.analytics_service import LoadAnalyticsService


def _json(result_tuple):
    data, status = result_tuple
    return JsonResponse(data, status=status)


@csrf_exempt
@require_GET
@require_permission("analytics.view")
def overview(request):
    return _json(LoadAnalyticsService.overview())


@csrf_exempt
@require_GET
@require_permission("analytics.view")
def load_frequency(request):
    period = request.GET.get("period", "7d").strip()
    page = request.GET.get("page", "1")
    per_page = request.GET.get("per_page", "20")
    min_count = request.GET.get("min_count", "2")
    sort_by = request.GET.get("sort_by", "-count").strip()

    try:
        page = max(1, int(page))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(100, max(1, int(per_page)))
    except (ValueError, TypeError):
        per_page = 20
    try:
        min_count = max(1, int(min_count))
    except (ValueError, TypeError):
        min_count = 2

    return _json(LoadAnalyticsService.load_frequency(
        period=period, page=page, per_page=per_page,
        min_count=min_count, sort_by=sort_by,
    ))


@csrf_exempt
@require_GET
@require_permission("analytics.view")
def route_frequency(request):
    period = request.GET.get("period", "7d").strip()
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

    return _json(LoadAnalyticsService.route_frequency(
        period=period, page=page, per_page=per_page,
    ))


@csrf_exempt
@require_GET
@require_permission("analytics.view")
def trends(request):
    period = request.GET.get("period", "30d").strip()
    group_by = request.GET.get("group_by", "day").strip()
    if group_by not in ("day", "week"):
        group_by = "day"

    return _json(LoadAnalyticsService.trends(period=period, group_by=group_by))


@csrf_exempt
@require_GET
@require_permission("analytics.compare")
def compare_periods(request):
    period_a = request.GET.get("period_a", "7d").strip()
    period_b = request.GET.get("period_b", "14d").strip()

    return _json(LoadAnalyticsService.compare_periods(
        period_a=period_a, period_b=period_b,
    ))
