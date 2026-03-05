from django.db import transaction
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
from datetime import timedelta

from base.models import Load, LoadLeg, Stop, User
from base.services.base_service import ServiceResponse, CacheService


class LoadService:

    VALID_STATUS_TRANSITIONS = {
        "available": ["booked", "cancelled"],
        "booked": ["in_transit", "cancelled"],
        "in_transit": ["delivered"],
        "delivered": [],
        "cancelled": [],
    }

    CACHE_TTL = 120  # 2 minutes for list caches
    DETAIL_TTL = 300  # 5 minutes for detail caches

    @classmethod
    def _invalidate_load_caches(cls, load_id=None):
        CacheService.delete_pattern("loads:list:*")
        CacheService.delete_pattern("loads:stats")
        CacheService.delete_pattern("loads:my:*")
        if load_id:
            CacheService.delete(f"loads:detail:{load_id}")

    @classmethod
    def list_loads(cls, page=1, per_page=20, status="", origin="",
                   destination="", driver_id=None, search="",
                   sort_by="-created_at") -> tuple:
        cache_key = f"loads:list:{page}:{per_page}:{status}:{origin}:{destination}:{driver_id}:{search}:{sort_by}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Loads retrieved", data=cached)

        qs = Load.objects.all()

        if status:
            qs = qs.filter(status=status)
        if origin:
            qs = qs.filter(
                Q(origin_facility__icontains=origin) |
                Q(origin_city__icontains=origin) |
                Q(origin_state__icontains=origin) |
                Q(origin_address__icontains=origin) |
                Q(origin_zip__icontains=origin)
            )
        if destination:
            qs = qs.filter(
                Q(destination_facility__icontains=destination) |
                Q(destination_city__icontains=destination) |
                Q(destination_state__icontains=destination) |
                Q(destination_address__icontains=destination) |
                Q(destination_zip__icontains=destination)
            )
        if driver_id:
            qs = qs.filter(assigned_driver_id=driver_id)
        if search:
            qs = qs.filter(
                Q(load_id__icontains=search) |
                Q(tour_id__icontains=search) |
                Q(origin_facility__icontains=search) |
                Q(destination_facility__icontains=search) |
                Q(origin_city__icontains=search) |
                Q(destination_city__icontains=search) |
                Q(origin_state__icontains=search) |
                Q(destination_state__icontains=search) |
                Q(special_services__icontains=search) |
                Q(equipment_type__icontains=search)
            )

        allowed_sorts = {
            "created_at", "-created_at", "payout", "-payout",
            "total_miles", "-total_miles", "origin_datetime", "-origin_datetime",
            "destination_datetime", "-destination_datetime",
            "rate_per_mile", "-rate_per_mile", "status", "-status",
            "id", "-id",
        }
        if sort_by not in allowed_sorts:
            sort_by = "-created_at"

        qs = qs.order_by(sort_by)
        total = qs.count()
        offset = (page - 1) * per_page
        loads = qs.select_related("registered_by", "assigned_driver")[offset:offset + per_page]

        result_data = {
            "loads": [cls._serialize_load_list(l) for l in loads],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": max(1, (total + per_page - 1) // per_page),
            },
        }
        CacheService.set(cache_key, result_data, cls.CACHE_TTL)
        return ServiceResponse.success("Loads retrieved", data=result_data)

    @classmethod
    def get_load(cls, load_id: int) -> tuple:
        cache_key = f"loads:detail:{load_id}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Load retrieved", data=cached)

        try:
            load = (
                Load.objects
                .select_related("registered_by", "assigned_driver")
                .prefetch_related("legs", "stops")
                .get(pk=load_id)
            )
        except Load.DoesNotExist:
            return ServiceResponse.not_found("Load not found")

        data = cls._serialize_load_detail(load)
        CacheService.set(cache_key, data, cls.DETAIL_TTL)
        return ServiceResponse.success("Load retrieved", data=data)

    @classmethod
    @transaction.atomic
    def create_load(cls, user, **fields) -> tuple:
        legs_data = fields.pop("legs", [])
        stops_data = fields.pop("stops", [])

        load = Load.objects.create(registered_by=user, **fields)

        for leg in legs_data:
            LoadLeg.objects.create(load=load, **leg)

        for stop in stops_data:
            Stop.objects.create(load=load, **stop)

        load = (
            Load.objects
            .select_related("registered_by", "assigned_driver")
            .prefetch_related("legs", "stops")
            .get(pk=load.pk)
        )

        cls._invalidate_load_caches()

        return ServiceResponse.success(
            "Load created successfully",
            data=cls._serialize_load_detail(load),
            status=201,
        )

    @classmethod
    @transaction.atomic
    def update_load(cls, load_id: int, **fields) -> tuple:
        try:
            load = Load.objects.get(pk=load_id)
        except Load.DoesNotExist:
            return ServiceResponse.not_found("Load not found")

        if load.status in ("delivered", "cancelled"):
            return ServiceResponse.error("Cannot update a completed or cancelled load")

        update_fields = []
        for field, value in fields.items():
            setattr(load, field, value)
            update_fields.append(field)

        load.save(update_fields=update_fields)

        load = (
            Load.objects
            .select_related("registered_by", "assigned_driver")
            .prefetch_related("legs", "stops")
            .get(pk=load.pk)
        )

        cls._invalidate_load_caches(load_id)

        return ServiceResponse.success(
            "Load updated successfully",
            data=cls._serialize_load_detail(load),
        )

    @classmethod
    @transaction.atomic
    def cancel_load(cls, load_id: int) -> tuple:
        try:
            load = Load.objects.get(pk=load_id)
        except Load.DoesNotExist:
            return ServiceResponse.not_found("Load not found")

        if load.status in ("delivered", "cancelled"):
            return ServiceResponse.error(f"Cannot cancel a load with status '{load.status}'")

        load.status = "cancelled"
        load.save(update_fields=["status"])

        cls._invalidate_load_caches(load_id)

        return ServiceResponse.success("Load cancelled successfully")

    @classmethod
    @transaction.atomic
    def assign_driver(cls, load_id: int, driver_id: int) -> tuple:
        try:
            load = Load.objects.get(pk=load_id)
        except Load.DoesNotExist:
            return ServiceResponse.not_found("Load not found")

        if load.status not in ("available", "booked"):
            return ServiceResponse.error("Can only assign driver to available or booked loads")

        try:
            driver = User.objects.get(pk=driver_id, is_active=True)
        except User.DoesNotExist:
            return ServiceResponse.not_found("Driver not found")

        load.assigned_driver = driver
        if load.status == "available":
            load.status = "booked"
            load.save(update_fields=["assigned_driver", "status"])
        else:
            load.save(update_fields=["assigned_driver"])

        cls._invalidate_load_caches(load_id)

        return ServiceResponse.success("Driver assigned successfully", data={
            "load_id": load.pk,
            "assigned_driver": driver_id,
            "status": load.status,
        })

    @classmethod
    @transaction.atomic
    def update_status(cls, load_id: int, status: str) -> tuple:
        try:
            load = Load.objects.get(pk=load_id)
        except Load.DoesNotExist:
            return ServiceResponse.not_found("Load not found")

        allowed = cls.VALID_STATUS_TRANSITIONS.get(load.status, [])
        if status not in allowed:
            return ServiceResponse.error(
                f"Cannot transition from '{load.status}' to '{status}'. "
                f"Allowed: {', '.join(allowed) if allowed else 'none'}"
            )

        load.status = status
        load.save(update_fields=["status"])

        cls._invalidate_load_caches(load_id)

        return ServiceResponse.success("Status updated", data={
            "load_id": load.pk,
            "status": load.status,
        })

    @classmethod
    def my_loads(cls, user, page=1, per_page=20) -> tuple:
        cache_key = f"loads:my:{user.pk}:{page}:{per_page}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("My loads retrieved", data=cached)

        qs = Load.objects.filter(assigned_driver=user).order_by("-created_at")

        total = qs.count()
        offset = (page - 1) * per_page
        loads = qs.select_related("registered_by", "assigned_driver")[offset:offset + per_page]

        result_data = {
            "loads": [cls._serialize_load_list(l) for l in loads],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": max(1, (total + per_page - 1) // per_page),
            },
        }
        CacheService.set(cache_key, result_data, cls.CACHE_TTL)
        return ServiceResponse.success("My loads retrieved", data=result_data)

    @classmethod
    def stats(cls) -> tuple:
        cache_key = "loads:stats"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Load statistics", data=cached)

        now = timezone.now()
        total = Load.objects.count()

        status_breakdown = dict(
            Load.objects.values_list("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        last_24h = Load.objects.filter(created_at__gte=now - timedelta(hours=24)).count()
        last_7d = Load.objects.filter(created_at__gte=now - timedelta(days=7)).count()
        last_30d = Load.objects.filter(created_at__gte=now - timedelta(days=30)).count()

        financial = Load.objects.exclude(status="cancelled").aggregate(
            total_payout=Sum("payout"),
            avg_payout=Avg("payout"),
            sum_miles=Sum("total_miles"),
            avg_miles=Avg("total_miles"),
            avg_rate=Avg("rate_per_mile"),
        )

        delivered = Load.objects.filter(
            status="delivered",
            created_at__gte=now - timedelta(days=30),
        ).count()

        top_origins = list(
            Load.objects.values("origin_facility", "origin_city", "origin_state")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        top_destinations = list(
            Load.objects.values("destination_facility", "destination_city", "destination_state")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        data = {
            "total_loads": total,
            "status_breakdown": {
                "available": status_breakdown.get("available", 0),
                "booked": status_breakdown.get("booked", 0),
                "in_transit": status_breakdown.get("in_transit", 0),
                "delivered": status_breakdown.get("delivered", 0),
                "cancelled": status_breakdown.get("cancelled", 0),
            },
            "new_last_24h": last_24h,
            "new_last_7d": last_7d,
            "new_last_30d": last_30d,
            "delivered_last_30d": delivered,
            "financial": {
                "total_payout": str(financial["total_payout"] or 0),
                "avg_payout": str(round(financial["avg_payout"] or 0, 2)),
                "total_miles": str(financial["sum_miles"] or 0),
                "avg_miles": str(round(financial["avg_miles"] or 0, 1)),
                "avg_rate_per_mile": str(round(financial["avg_rate"] or 0, 2)),
            },
            "top_origins": top_origins,
            "top_destinations": top_destinations,
        }

        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("Load statistics", data=data)

    # -- serializers --

    @classmethod
    def _serialize_load_list(cls, load: Load) -> dict:
        return {
            "id": load.pk,
            "load_id": load.load_id,
            "tour_id": load.tour_id,
            "origin_facility": load.origin_facility,
            "origin_city": load.origin_city,
            "origin_state": load.origin_state,
            "destination_facility": load.destination_facility,
            "destination_city": load.destination_city,
            "destination_state": load.destination_state,
            "origin_datetime": load.origin_datetime.isoformat() if load.origin_datetime else None,
            "destination_datetime": load.destination_datetime.isoformat() if load.destination_datetime else None,
            "total_stops": load.total_stops,
            "total_miles": str(load.total_miles),
            "payout": str(load.payout),
            "rate_per_mile": str(load.rate_per_mile) if load.rate_per_mile else None,
            "driver_type": load.driver_type,
            "load_type": load.load_type,
            "status": load.status,
            "assigned_driver": {
                "id": load.assigned_driver.pk,
                "full_name": load.assigned_driver.full_name,
            } if load.assigned_driver else None,
            "created_at": load.created_at.isoformat() if load.created_at else None,
        }

    @classmethod
    def _serialize_load_detail(cls, load: Load) -> dict:
        data = cls._serialize_load_list(load)
        data.update({
            "origin_address": load.origin_address,
            "origin_zip": load.origin_zip,
            "origin_timezone": load.origin_timezone,
            "destination_address": load.destination_address,
            "destination_zip": load.destination_zip,
            "destination_timezone": load.destination_timezone,
            "deadhead_miles": str(load.deadhead_miles),
            "base_rate_per_mile": str(load.base_rate_per_mile) if load.base_rate_per_mile else None,
            "toll": str(load.toll),
            "profit_per_mile": str(load.profit_per_mile),
            "equipment_type": load.equipment_type,
            "equipment_provided": load.equipment_provided,
            "direction": load.direction,
            "duration": load.duration,
            "special_services": load.special_services,
            "registered_by": {
                "id": load.registered_by.pk,
                "full_name": load.registered_by.full_name,
            },
            "updated_at": load.updated_at.isoformat() if load.updated_at else None,
            "legs": [cls._serialize_leg(leg) for leg in load.legs.all()],
            "stops": [cls._serialize_stop(stop) for stop in load.stops.all()],
        })
        return data

    @classmethod
    def _serialize_leg(cls, leg: LoadLeg) -> dict:
        return {
            "id": leg.pk,
            "leg_number": leg.leg_number,
            "leg_code": leg.leg_code,
            "origin_facility": leg.origin_facility,
            "destination_facility": leg.destination_facility,
            "miles": str(leg.miles),
            "duration": leg.duration,
            "payout": str(leg.payout) if leg.payout else None,
            "load_type": leg.load_type,
            "status": leg.status,
        }

    @classmethod
    def _serialize_stop(cls, stop: Stop) -> dict:
        return {
            "id": stop.pk,
            "stop_number": stop.stop_number,
            "facility_code": stop.facility_code,
            "address": stop.address,
            "city": stop.city,
            "state": stop.state,
            "zip_code": stop.zip_code,
            "equipment": stop.equipment,
            "arrival_at": stop.arrival_at.isoformat() if stop.arrival_at else None,
            "arrival_timezone": stop.arrival_timezone,
            "departure_at": stop.departure_at.isoformat() if stop.departure_at else None,
            "departure_timezone": stop.departure_timezone,
            "miles_to_next": str(stop.miles_to_next) if stop.miles_to_next else None,
        }
