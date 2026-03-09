from django.db.models import Count, Sum, Min, Max, Q
from django.db.models.functions import TruncWeek, TruncMonth, TruncYear
from django.utils.dateparse import parse_date
from datetime import timedelta

from base.models import Load, Route, State
from base.services.base_service import ServiceResponse, CacheService


class RouteService:

    CACHE_TTL = 120
    DETAIL_TTL = 300

    # ── list all states ──────────────────────────────────────────────

    @classmethod
    def list_states(cls, loads=False, page=1, per_page=20) -> tuple:
        cache_key = f"states:list:{loads}:{page}:{per_page}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("States retrieved", data=cached)

        states = list(
            State.objects.values("abbreviation", "name").order_by("abbreviation")
        )

        if not loads:
            data = {"states": states, "total": len(states)}
            CacheService.set(cache_key, data, cls.DETAIL_TTL)
            return ServiceResponse.success("States retrieved", data=data)

        # loads=true: show routes grouped by state with their loads
        routes_qs = (
            Route.objects
            .select_related("origin_state", "destination_state")
            .annotate(
                load_count=Count("loads"),
                total_payout=Sum("loads__payout"),
                most_expensive=Max("loads__payout"),
                cheapest=Min("loads__payout"),
                total_miles=Sum("loads__total_miles"),
            )
            .filter(load_count__gt=0)
            .order_by("-load_count")
        )

        total_routes = routes_qs.count()
        offset = (page - 1) * per_page
        routes_page = list(routes_qs[offset:offset + per_page])

        # fetch loads for each route on this page
        from main.services.load_service import LoadService

        route_ids = [r.pk for r in routes_page]
        all_loads = (
            Load.objects.filter(route_id__in=route_ids)
            .select_related("registered_by", "assigned_driver", "route")
            .order_by("-payout")
        )

        loads_by_route = {}
        for load in all_loads:
            loads_by_route.setdefault(load.route_id, []).append(load)

        routes_data = []
        for r in routes_page:
            route_loads = loads_by_route.get(r.pk, [])
            routes_data.append({
                "route_id": r.route_id,
                "origin_state": r.origin_state.abbreviation,
                "destination_state": r.destination_state.abbreviation,
                "load_count": r.load_count,
                "total_payout": str(r.total_payout or 0),
                "most_expensive": str(r.most_expensive or 0),
                "cheapest": str(r.cheapest or 0),
                "total_miles": str(r.total_miles or 0),
                "loads": [LoadService._serialize_load_list(l) for l in route_loads],
            })

        data = {
            "routes": routes_data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_routes,
                "pages": max(1, (total_routes + per_page - 1) // per_page),
            },
        }
        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("States with loads retrieved", data=data)

    # ── list routes ──────────────────────────────────────────────────

    @classmethod
    def list_routes(cls, page=1, per_page=20, search="",
                    sort_by="-load_count", loads=False,
                    week=None, date_from=None, date_to=None) -> tuple:
        cache_key = f"routes:list:{page}:{per_page}:{search}:{sort_by}:{loads}:{week}:{date_from}:{date_to}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Routes retrieved", data=cached)

        qs = Route.objects.select_related("origin_state", "destination_state")

        if search:
            search_upper = search.upper()
            qs = qs.filter(
                Q(route_id__icontains=search_upper) |
                Q(origin_state__name__icontains=search) |
                Q(destination_state__name__icontains=search) |
                Q(origin_state__abbreviation__icontains=search_upper) |
                Q(destination_state__abbreviation__icontains=search_upper)
            )

        # build load filter for date/week constraints
        load_filter = Q()
        if week:
            week_date = parse_date(week) if isinstance(week, str) else week
            if week_date:
                monday = week_date - timedelta(days=week_date.weekday())
                sunday = monday + timedelta(days=7)
                load_filter &= Q(loads__created_at__date__gte=monday)
                load_filter &= Q(loads__created_at__date__lt=sunday)
        else:
            if date_from:
                d = parse_date(date_from) if isinstance(date_from, str) else date_from
                if d:
                    load_filter &= Q(loads__created_at__date__gte=d)
            if date_to:
                d = parse_date(date_to) if isinstance(date_to, str) else date_to
                if d:
                    load_filter &= Q(loads__created_at__date__lte=d)

        qs = qs.annotate(
            load_count=Count("loads", filter=load_filter) if load_filter else Count("loads"),
            total_payout=Sum("loads__payout", filter=load_filter) if load_filter else Sum("loads__payout"),
            most_expensive=Max("loads__payout", filter=load_filter) if load_filter else Max("loads__payout"),
            cheapest=Min("loads__payout", filter=load_filter) if load_filter else Min("loads__payout"),
            total_miles=Sum("loads__total_miles", filter=load_filter) if load_filter else Sum("loads__total_miles"),
            latest_load=Max("loads__created_at", filter=load_filter) if load_filter else Max("loads__created_at"),
        )

        qs = qs.filter(load_count__gt=0)

        allowed_sorts = {
            "load_count", "-load_count", "total_payout", "-total_payout",
            "most_expensive", "-most_expensive", "cheapest", "-cheapest",
            "route_id", "-route_id", "latest_load", "-latest_load",
        }
        if sort_by not in allowed_sorts:
            sort_by = "-load_count"
        qs = qs.order_by(sort_by)

        total = qs.count()
        offset = (page - 1) * per_page
        routes = list(qs[offset:offset + per_page])

        if not loads:
            result_data = {
                "routes": [cls._serialize_route(r) for r in routes],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "pages": max(1, (total + per_page - 1) // per_page),
                },
            }
        else:
            # loads=true: include actual loads inside each route
            from main.services.load_service import LoadService

            route_pks = [r.pk for r in routes]
            loads_qs = (
                Load.objects.filter(route_id__in=route_pks)
                .select_related("registered_by", "assigned_driver", "route")
            )
            # apply same date filters to loads
            if week:
                week_date = parse_date(week) if isinstance(week, str) else week
                if week_date:
                    monday = week_date - timedelta(days=week_date.weekday())
                    sunday = monday + timedelta(days=7)
                    loads_qs = loads_qs.filter(
                        created_at__date__gte=monday, created_at__date__lt=sunday
                    )
            else:
                if date_from:
                    d = parse_date(date_from) if isinstance(date_from, str) else date_from
                    if d:
                        loads_qs = loads_qs.filter(created_at__date__gte=d)
                if date_to:
                    d = parse_date(date_to) if isinstance(date_to, str) else date_to
                    if d:
                        loads_qs = loads_qs.filter(created_at__date__lte=d)

            loads_qs = loads_qs.order_by("-payout")

            loads_by_route = {}
            for load in loads_qs:
                loads_by_route.setdefault(load.route_id, []).append(load)

            routes_data = []
            for r in routes:
                route_loads = loads_by_route.get(r.pk, [])
                rdata = cls._serialize_route(r)
                rdata["loads"] = [LoadService._serialize_load_list(l) for l in route_loads]
                routes_data.append(rdata)

            result_data = {
                "routes": routes_data,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "pages": max(1, (total + per_page - 1) // per_page),
                },
            }

        CacheService.set(cache_key, result_data, cls.CACHE_TTL)
        return ServiceResponse.success("Routes retrieved", data=result_data)

    # ── route detail ─────────────────────────────────────────────────

    @classmethod
    def get_route(cls, route_id: str) -> tuple:
        route_id = route_id.upper()
        cache_key = f"routes:detail:{route_id}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Route retrieved", data=cached)

        try:
            route = (
                Route.objects
                .select_related("origin_state", "destination_state")
                .annotate(
                    load_count=Count("loads"),
                    total_payout=Sum("loads__payout"),
                    most_expensive=Max("loads__payout"),
                    cheapest=Min("loads__payout"),
                    total_miles=Sum("loads__total_miles"),
                    latest_load=Max("loads__created_at"),
                    earliest_load=Min("loads__created_at"),
                )
                .get(route_id=route_id)
            )
        except Route.DoesNotExist:
            return ServiceResponse.not_found("Route not found")

        # status breakdown
        status_counts = dict(
            Load.objects.filter(route=route)
            .values_list("status")
            .annotate(c=Count("id"))
            .values_list("status", "c")
        )

        data = cls._serialize_route(route)
        data.update({
            "earliest_load": route.earliest_load.isoformat() if route.earliest_load else None,
            "status_breakdown": {
                "available": status_counts.get("available", 0),
                "booked": status_counts.get("booked", 0),
                "in_transit": status_counts.get("in_transit", 0),
                "delivered": status_counts.get("delivered", 0),
                "cancelled": status_counts.get("cancelled", 0),
            },
        })

        CacheService.set(cache_key, data, cls.DETAIL_TTL)
        return ServiceResponse.success("Route retrieved", data=data)

    # ── loads for a route ────────────────────────────────────────────

    @classmethod
    def route_loads(cls, route_id: str, page=1, per_page=20,
                    status="", sort_by="-created_at",
                    week=None, date_from=None, date_to=None,
                    min_payout=None, max_payout=None) -> tuple:
        route_id = route_id.upper()
        cache_key = (
            f"routes:loads:{route_id}:{page}:{per_page}:{status}:"
            f"{sort_by}:{week}:{date_from}:{date_to}:{min_payout}:{max_payout}"
        )
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Route loads retrieved", data=cached)

        try:
            route = Route.objects.get(route_id=route_id)
        except Route.DoesNotExist:
            return ServiceResponse.not_found("Route not found")

        qs = Load.objects.filter(route=route).select_related(
            "registered_by", "assigned_driver", "route"
        )

        if status:
            qs = qs.filter(status=status)
        if min_payout is not None:
            qs = qs.filter(payout__gte=min_payout)
        if max_payout is not None:
            qs = qs.filter(payout__lte=max_payout)

        if week:
            week_date = parse_date(week) if isinstance(week, str) else week
            if week_date:
                monday = week_date - timedelta(days=week_date.weekday())
                sunday = monday + timedelta(days=7)
                qs = qs.filter(created_at__date__gte=monday, created_at__date__lt=sunday)
        else:
            if date_from:
                d = parse_date(date_from) if isinstance(date_from, str) else date_from
                if d:
                    qs = qs.filter(created_at__date__gte=d)
            if date_to:
                d = parse_date(date_to) if isinstance(date_to, str) else date_to
                if d:
                    qs = qs.filter(created_at__date__lte=d)

        allowed_sorts = {
            "created_at", "-created_at", "payout", "-payout",
            "total_miles", "-total_miles", "origin_datetime", "-origin_datetime",
            "rate_per_mile", "-rate_per_mile",
        }
        if sort_by not in allowed_sorts:
            sort_by = "-created_at"
        qs = qs.order_by(sort_by)

        total = qs.count()
        offset = (page - 1) * per_page
        loads = qs[offset:offset + per_page]

        from main.services.load_service import LoadService

        # route-level totals for the filtered set
        totals = Load.objects.filter(route=route)
        if status:
            totals = totals.filter(status=status)
        if min_payout is not None:
            totals = totals.filter(payout__gte=min_payout)
        if max_payout is not None:
            totals = totals.filter(payout__lte=max_payout)
        if week:
            week_date = parse_date(week) if isinstance(week, str) else week
            if week_date:
                monday = week_date - timedelta(days=week_date.weekday())
                sunday = monday + timedelta(days=7)
                totals = totals.filter(created_at__date__gte=monday, created_at__date__lt=sunday)
        elif date_from or date_to:
            if date_from:
                d = parse_date(date_from) if isinstance(date_from, str) else date_from
                if d:
                    totals = totals.filter(created_at__date__gte=d)
            if date_to:
                d = parse_date(date_to) if isinstance(date_to, str) else date_to
                if d:
                    totals = totals.filter(created_at__date__lte=d)

        agg = totals.aggregate(
            total_loads=Count("id"),
            total_payout=Sum("payout"),
            most_expensive=Max("payout"),
            cheapest=Min("payout"),
            total_miles=Sum("total_miles"),
        )

        result_data = {
            "route_id": route.route_id,
            "totals": {
                "total_loads": agg["total_loads"] or 0,
                "total_payout": str(agg["total_payout"] or 0),
                "most_expensive": str(agg["most_expensive"] or 0),
                "cheapest": str(agg["cheapest"] or 0),
                "total_miles": str(agg["total_miles"] or 0),
            },
            "loads": [LoadService._serialize_load_list(l) for l in loads],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": max(1, (total + per_page - 1) // per_page),
            },
        }
        CacheService.set(cache_key, result_data, cls.CACHE_TTL)
        return ServiceResponse.success("Route loads retrieved", data=result_data)

    # ── route analytics (weekly / monthly / yearly) ──────────────────

    @classmethod
    def route_analytics(cls, route_id: str, period="weekly") -> tuple:
        route_id = route_id.upper()
        cache_key = f"routes:analytics:{route_id}:{period}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Route analytics", data=cached)

        try:
            route = Route.objects.select_related(
                "origin_state", "destination_state"
            ).get(route_id=route_id)
        except Route.DoesNotExist:
            return ServiceResponse.not_found("Route not found")

        qs = Load.objects.filter(route=route)

        if period == "monthly":
            trunc_fn = TruncMonth
        elif period == "yearly":
            trunc_fn = TruncYear
        else:
            trunc_fn = TruncWeek
            period = "weekly"

        time_data = list(
            qs.annotate(time_period=trunc_fn("created_at"))
            .values("time_period")
            .annotate(
                total_loads=Count("id"),
                total_payout=Sum("payout"),
                most_expensive=Max("payout"),
                cheapest=Min("payout"),
                total_miles=Sum("total_miles"),
                available=Count("id", filter=Q(status="available")),
                booked=Count("id", filter=Q(status="booked")),
                in_transit=Count("id", filter=Q(status="in_transit")),
                delivered=Count("id", filter=Q(status="delivered")),
                cancelled=Count("id", filter=Q(status="cancelled")),
            )
            .order_by("-time_period")
        )

        # overall totals (no averages)
        overall = qs.aggregate(
            total_loads=Count("id"),
            total_payout=Sum("payout"),
            most_expensive=Max("payout"),
            cheapest=Min("payout"),
            total_miles=Sum("total_miles"),
        )

        periods_list = []
        for row in time_data:
            periods_list.append({
                "period": row["time_period"].isoformat() if row["time_period"] else None,
                "total_loads": row["total_loads"],
                "total_payout": str(row["total_payout"] or 0),
                "most_expensive": str(row["most_expensive"] or 0),
                "cheapest": str(row["cheapest"] or 0),
                "total_miles": str(row["total_miles"] or 0),
                "status_breakdown": {
                    "available": row["available"],
                    "booked": row["booked"],
                    "in_transit": row["in_transit"],
                    "delivered": row["delivered"],
                    "cancelled": row["cancelled"],
                },
            })

        data = {
            "route_id": route.route_id,
            "origin_state": {
                "abbreviation": route.origin_state.abbreviation,
                "name": route.origin_state.name,
            },
            "destination_state": {
                "abbreviation": route.destination_state.abbreviation,
                "name": route.destination_state.name,
            },
            "period_type": period,
            "summary": {
                "total_loads": overall["total_loads"] or 0,
                "total_payout": str(overall["total_payout"] or 0),
                "most_expensive": str(overall["most_expensive"] or 0),
                "cheapest": str(overall["cheapest"] or 0),
                "total_miles": str(overall["total_miles"] or 0),
            },
            "periods": periods_list,
        }

        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("Route analytics", data=data)

    # ── cache invalidation ───────────────────────────────────────────

    @classmethod
    def invalidate_route_caches(cls, route_id=None):
        CacheService.delete_pattern("routes:list:*")
        CacheService.delete_pattern("states:list:*")
        if route_id:
            CacheService.delete(f"routes:detail:{route_id}")
            CacheService.delete_pattern(f"routes:loads:{route_id}:*")
            CacheService.delete_pattern(f"routes:analytics:{route_id}:*")

    # ── serializer ───────────────────────────────────────────────────

    @classmethod
    def _serialize_route(cls, route) -> dict:
        return {
            "route_id": route.route_id,
            "origin_state": {
                "abbreviation": route.origin_state.abbreviation,
                "name": route.origin_state.name,
            },
            "destination_state": {
                "abbreviation": route.destination_state.abbreviation,
                "name": route.destination_state.name,
            },
            "load_count": route.load_count,
            "total_payout": str(route.total_payout or 0),
            "most_expensive": str(route.most_expensive or 0),
            "cheapest": str(route.cheapest or 0),
            "total_miles": str(route.total_miles or 0),
            "latest_load": route.latest_load.isoformat() if route.latest_load else None,
            "created_at": route.created_at.isoformat() if route.created_at else None,
        }
