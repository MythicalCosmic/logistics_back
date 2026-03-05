from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from base.decorators.decorators import require_auth
from main.services.facility_service import FacilityService
from main.requests.facility_requests import list_facilities_request


def _json(result_tuple):
    data, status = result_tuple
    return JsonResponse(data, status=status)


@csrf_exempt
@require_GET
@require_auth
def list_facilities(request):
    data, error = list_facilities_request(request)
    if error:
        return _json(error)

    return _json(FacilityService.list_facilities(
        page=data["page"],
        per_page=data["per_page"],
        facility_type=data.get("facility_type", ""),
        state=data.get("state", ""),
        city=data.get("city", ""),
        search=data.get("search", ""),
    ))


@csrf_exempt
@require_GET
@require_auth
def get_facility(request, facility_id):
    return _json(FacilityService.get_facility(facility_id))
