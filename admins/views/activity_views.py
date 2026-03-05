from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from base.decorators.decorators import require_permission
from admins.services.activity_service import AdminActivityService


def _json(result_tuple):
    data, status = result_tuple
    return JsonResponse(data, status=status)


@csrf_exempt
@require_GET
@require_permission("reports.view")
def list_logs(request):
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

    user_id = request.GET.get("user_id")
    if user_id:
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = None

    load_id = request.GET.get("load_id")
    if load_id:
        try:
            load_id = int(load_id)
        except (ValueError, TypeError):
            load_id = None

    return _json(AdminActivityService.list_logs(
        page=page,
        per_page=per_page,
        user_id=user_id,
        action=request.GET.get("action", "").strip(),
        load_id=load_id,
        date_from=request.GET.get("date_from"),
        date_to=request.GET.get("date_to"),
        search=request.GET.get("search", "").strip(),
    ))


@csrf_exempt
@require_GET
@require_permission("reports.view")
def get_log(request, log_id):
    return _json(AdminActivityService.get_log(log_id))
