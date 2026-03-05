from django.db.models import Q

from base.models import Facility
from base.services.base_service import ServiceResponse, CacheService


class FacilityService:

    CACHE_TTL = 300  # 5 minutes

    @classmethod
    def list_facilities(cls, page=1, per_page=20, facility_type="",
                        state="", city="", search="") -> tuple:
        cache_key = f"facilities:list:{page}:{per_page}:{facility_type}:{state}:{city}:{search}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Facilities retrieved", data=cached)

        qs = Facility.objects.all()

        if facility_type:
            qs = qs.filter(facility_type=facility_type)
        if state:
            qs = qs.filter(state__iexact=state)
        if city:
            qs = qs.filter(city__icontains=city)
        if search:
            qs = qs.filter(
                Q(code__icontains=search) |
                Q(name__icontains=search) |
                Q(city__icontains=search) |
                Q(state__icontains=search) |
                Q(address__icontains=search) |
                Q(zip_code__icontains=search)
            )

        total = qs.count()
        offset = (page - 1) * per_page
        facilities = qs[offset:offset + per_page]

        result_data = {
            "facilities": [cls._serialize(f) for f in facilities],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": max(1, (total + per_page - 1) // per_page),
            },
        }
        CacheService.set(cache_key, result_data, cls.CACHE_TTL)
        return ServiceResponse.success("Facilities retrieved", data=result_data)

    @classmethod
    def get_facility(cls, facility_id: int) -> tuple:
        cache_key = f"facilities:detail:{facility_id}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Facility retrieved", data=cached)

        try:
            facility = Facility.objects.get(pk=facility_id)
        except Facility.DoesNotExist:
            return ServiceResponse.not_found("Facility not found")

        data = cls._serialize(facility)
        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("Facility retrieved", data=data)

    @classmethod
    def _serialize(cls, f: Facility) -> dict:
        return {
            "id": f.pk,
            "code": f.code,
            "name": f.name,
            "address": f.address,
            "city": f.city,
            "state": f.state,
            "zip_code": f.zip_code,
            "facility_type": f.facility_type,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
