from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from base.decorators.decorators import require_permission
from admins.services.facility_service import AdminFacilityService
from admins.requests.facility_requests import (
    create_facility_request,
    update_facility_request,
    list_facilities_request,
)


def _json(result_tuple):
    data, status = result_tuple
    return JsonResponse(data, status=status)


@csrf_exempt
@require_GET
@require_permission("facilities.view")
def list_facilities(request):
    data, error = list_facilities_request(request)
    if error:
        return _json(error)

    return _json(AdminFacilityService.list_facilities(
        page=data["page"],
        per_page=data["per_page"],
        facility_type=data.get("facility_type", ""),
        state=data.get("state", ""),
        city=data.get("city", ""),
        search=data.get("search", ""),
    ))


@csrf_exempt
@require_POST
@require_permission("facilities.create")
def create_facility(request):
    data, error = create_facility_request(request)
    if error:
        return _json(error)

    return _json(AdminFacilityService.create_facility(**data))


@csrf_exempt
@require_GET
@require_permission("facilities.view")
def get_facility(request, facility_id):
    return _json(AdminFacilityService.get_facility(facility_id))


@csrf_exempt
@require_http_methods(["PUT"])
@require_permission("facilities.update")
def update_facility(request, facility_id):
    data, error = update_facility_request(request)
    if error:
        return _json(error)

    return _json(AdminFacilityService.update_facility(facility_id, **data))


@csrf_exempt
@require_http_methods(["DELETE"])
@require_permission("facilities.delete")
def delete_facility(request, facility_id):
    return _json(AdminFacilityService.delete_facility(facility_id))


@csrf_exempt
@require_GET
@require_permission("facilities.view")
def facility_stats(request):
    return _json(AdminFacilityService.stats())
