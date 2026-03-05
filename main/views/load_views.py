from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from base.decorators.decorators import require_auth, require_permission
from main.services.load_service import LoadService
from main.requests.load_requests import (
    create_load_request,
    update_load_request,
    list_loads_request,
    assign_driver_request,
    update_status_request,
)


def _json(result_tuple):
    data, status = result_tuple
    return JsonResponse(data, status=status)


@csrf_exempt
@require_GET
@require_permission("loads.view")
def list_loads(request):
    data, error = list_loads_request(request)
    if error:
        return _json(error)

    return _json(LoadService.list_loads(
        page=data["page"],
        per_page=data["per_page"],
        status=data.get("status", ""),
        origin=data.get("origin", ""),
        destination=data.get("destination", ""),
        driver_id=data.get("driver_id"),
        search=data.get("search", ""),
        sort_by=data.get("sort_by", "-created_at"),
    ))


@csrf_exempt
@require_POST
@require_permission("loads.create")
def create_load(request):
    data, error = create_load_request(request)
    if error:
        return _json(error)

    return _json(LoadService.create_load(user=request.user, **data))


@csrf_exempt
@require_GET
@require_permission("loads.view")
def get_load(request, load_id):
    return _json(LoadService.get_load(load_id))


@csrf_exempt
@require_http_methods(["PUT"])
@require_permission("loads.update")
def update_load(request, load_id):
    data, error = update_load_request(request)
    if error:
        return _json(error)

    return _json(LoadService.update_load(load_id, **data))


@csrf_exempt
@require_POST
@require_permission("loads.update")
def cancel_load(request, load_id):
    return _json(LoadService.cancel_load(load_id))


@csrf_exempt
@require_POST
@require_permission("loads.assign")
def assign_driver(request, load_id):
    data, error = assign_driver_request(request)
    if error:
        return _json(error)

    return _json(LoadService.assign_driver(load_id, data["driver_id"]))


@csrf_exempt
@require_POST
@require_permission("loads.update")
def update_status(request, load_id):
    data, error = update_status_request(request)
    if error:
        return _json(error)

    return _json(LoadService.update_status(load_id, data["status"]))


@csrf_exempt
@require_GET
@require_auth
def my_loads(request):
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

    return _json(LoadService.my_loads(request.user, page=page, per_page=per_page))


@csrf_exempt
@require_GET
@require_permission("loads.view")
def load_stats(request):
    return _json(LoadService.stats())
