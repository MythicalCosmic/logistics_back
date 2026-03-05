from django.db import transaction
from django.db.models import Q, Count

from base.models import Facility, Load
from base.services.base_service import ServiceResponse, CacheService


class AdminFacilityService:

    CACHE_TTL = 300

    @classmethod
    def _invalidate_caches(cls, facility_id=None):
        CacheService.delete_pattern("facilities:*")
        CacheService.delete_pattern("admin:facilities:*")
        if facility_id:
            CacheService.delete(f"admin:facilities:detail:{facility_id}")

    @classmethod
    def list_facilities(cls, page=1, per_page=20, facility_type="",
                        state="", city="", search="") -> tuple:
        cache_key = f"admin:facilities:list:{page}:{per_page}:{facility_type}:{state}:{city}:{search}"
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
        cache_key = f"admin:facilities:detail:{facility_id}"
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
    @transaction.atomic
    def create_facility(cls, **fields) -> tuple:
        code = fields.get("code", "")
        if Facility.objects.filter(code=code).exists():
            return ServiceResponse.error("Facility code already exists")

        facility = Facility.objects.create(**fields)
        cls._invalidate_caches()

        return ServiceResponse.success(
            "Facility created successfully",
            data=cls._serialize(facility),
            status=201,
        )

    @classmethod
    @transaction.atomic
    def update_facility(cls, facility_id: int, **fields) -> tuple:
        try:
            facility = Facility.objects.get(pk=facility_id)
        except Facility.DoesNotExist:
            return ServiceResponse.not_found("Facility not found")

        if "code" in fields and fields["code"] != facility.code:
            if Facility.objects.filter(code=fields["code"]).exclude(pk=facility_id).exists():
                return ServiceResponse.error("Facility code already exists")

        update_fields = []
        for field, value in fields.items():
            setattr(facility, field, value)
            update_fields.append(field)

        facility.save(update_fields=update_fields)
        cls._invalidate_caches(facility_id)

        return ServiceResponse.success(
            "Facility updated successfully",
            data=cls._serialize(facility),
        )

    @classmethod
    @transaction.atomic
    def delete_facility(cls, facility_id: int) -> tuple:
        try:
            facility = Facility.objects.get(pk=facility_id)
        except Facility.DoesNotExist:
            return ServiceResponse.not_found("Facility not found")

        code = facility.code
        has_loads = Load.objects.filter(
            Q(origin_facility=code) | Q(destination_facility=code)
        ).exists()

        if has_loads:
            return ServiceResponse.error(
                "Cannot delete facility: it is referenced by existing loads"
            )

        facility.delete()
        cls._invalidate_caches(facility_id)
        return ServiceResponse.success("Facility deleted successfully")

    @classmethod
    def stats(cls) -> tuple:
        cache_key = "admin:facilities:stats"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Facility statistics", data=cached)

        total = Facility.objects.count()

        type_breakdown = dict(
            Facility.objects.values_list("facility_type")
            .annotate(count=Count("id"))
            .values_list("facility_type", "count")
        )

        top_states = list(
            Facility.objects.values("state")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        top_cities = list(
            Facility.objects.values("city", "state")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        data = {
            "total_facilities": total,
            "type_breakdown": type_breakdown,
            "top_states": top_states,
            "top_cities": top_cities,
        }

        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("Facility statistics", data=data)

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
