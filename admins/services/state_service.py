from datetime import timedelta

from django.db import connection
from django.db.models import Count, Sum, Min, Max, Q
from django.db.models.functions import TruncWeek, TruncMonth, TruncYear
from django.utils import timezone

from base.models import Load, Route, State
from base.services.base_service import ServiceResponse, CacheService


class StateService:

    CACHE_TTL = 120

    # ── helpers ───────────────────────────────────────────────────────

    @classmethod
    def _period_start(cls, period):
        """Return start datetime for a named period, or None for 'all'."""
        now = timezone.now()
        periods = {
            "weekly": now - timedelta(days=7),
            "monthly": now - timedelta(days=30),
            "yearly": now - timedelta(days=365),
        }
        return periods.get(period)

    @classmethod
    def _period_filter(cls, period):
        start = cls._period_start(period)
        if start:
            return Q(created_at__gte=start)
        return Q()

    @classmethod
    def _period_label(cls, period):
        labels = {
            "weekly": "Last 7 days",
            "monthly": "Last 30 days",
            "yearly": "Last 365 days",
        }
        return labels.get(period, "All time")

    # ── list all states with load counts ──────────────────────────────

    @classmethod
    def list_states(cls, page=1, per_page=20, search="",
                    period="all", sort_by="-load_count") -> tuple:
        cache_key = f"admin:states:{page}:{per_page}:{search}:{period}:{sort_by}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("States retrieved", data=cached)

        start = cls._period_start(period)

        # single raw SQL: aggregate loads per state (origin + destination)
        date_clause = ""
        params = []
        if start:
            date_clause = "AND l.created_at >= %s"
            params = [start, start]
        else:
            params = []

        sql = f"""
            SELECT
                s.abbreviation,
                s.name,
                COALESCE(o.cnt, 0) + COALESCE(d.cnt, 0) AS load_count,
                COALESCE(o.rcnt, 0) + COALESCE(d.rcnt, 0) AS route_count,
                ROUND(COALESCE(o.pay, 0) + COALESCE(d.pay, 0), 2) AS total_payout,
                MAX(COALESCE(o.exp, 0), COALESCE(d.exp, 0)) AS most_expensive,
                ROUND(COALESCE(o.miles, 0) + COALESCE(d.miles, 0), 1) AS total_miles
            FROM states s
            LEFT JOIN (
                SELECT r.origin_state_id AS st,
                       COUNT(l.id) AS cnt,
                       SUM(l.payout) AS pay,
                       MAX(l.payout) AS exp,
                       SUM(l.total_miles) AS miles,
                       COUNT(DISTINCT r.id) AS rcnt
                FROM routes r
                JOIN loads l ON l.route_id = r.id
                WHERE 1=1 {date_clause}
                GROUP BY r.origin_state_id
            ) o ON o.st = s.abbreviation
            LEFT JOIN (
                SELECT r.destination_state_id AS st,
                       COUNT(l.id) AS cnt,
                       SUM(l.payout) AS pay,
                       MAX(l.payout) AS exp,
                       SUM(l.total_miles) AS miles,
                       COUNT(DISTINCT r.id) AS rcnt
                FROM routes r
                JOIN loads l ON l.route_id = r.id
                WHERE 1=1 {date_clause}
                GROUP BY r.destination_state_id
            ) d ON d.st = s.abbreviation
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        # build items
        all_items = []
        for row in rows:
            abbr, name, load_count, route_count, total_payout, most_exp, total_miles = row
            all_items.append({
                "abbreviation": abbr,
                "name": name,
                "load_count": load_count or 0,
                "route_count": route_count or 0,
                "total_payout": str(total_payout or 0),
                "most_expensive": str(most_exp or 0),
                "total_miles": str(total_miles or 0),
            })

        # search filter (in Python since we already have all 50)
        if search:
            search_lower = search.lower()
            all_items = [
                s for s in all_items
                if search_lower in s["abbreviation"].lower()
                or search_lower in s["name"].lower()
            ]

        # sort
        reverse = sort_by.startswith("-")
        sort_field = sort_by.lstrip("-")
        if sort_field not in ("load_count", "abbreviation", "name"):
            sort_field = "load_count"
            reverse = True

        def sort_key(x):
            val = x.get(sort_field, "")
            if isinstance(val, str) and sort_field in ("abbreviation", "name"):
                return val.lower()
            return val

        all_items.sort(key=sort_key, reverse=reverse)

        total = len(all_items)
        offset = (page - 1) * per_page
        page_items = all_items[offset:offset + per_page]

        # most expensive load
        period_q = cls._period_filter(period)
        most_expensive_load = None
        top_load = (
            Load.objects.filter(period_q)
            .select_related("registered_by", "assigned_driver", "route")
            .order_by("-payout")
            .only(
                "id", "load_id", "tour_id", "route", "payout", "total_miles",
                "rate_per_mile", "status", "driver_type", "load_type",
                "total_stops", "origin_facility", "origin_city", "origin_state",
                "origin_datetime", "destination_facility", "destination_city",
                "destination_state", "destination_datetime", "created_at",
                "registered_by__id", "registered_by__first_name",
                "registered_by__last_name",
                "assigned_driver__id", "assigned_driver__first_name",
                "assigned_driver__last_name",
            )
            .first()
        )
        if top_load:
            from main.services.load_service import LoadService
            most_expensive_load = LoadService._serialize_load_list(top_load)

        data = {
            "period": cls._period_label(period),
            "most_expensive_load": most_expensive_load,
            "states": page_items,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": max(1, (total + per_page - 1) // per_page),
            },
        }
        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("States retrieved", data=data)

    # ── state detail: all routes for a state with loads ───────────────

    @classmethod
    def state_detail(cls, abbreviation, page=1, per_page=20,
                     search="", period="all", sort_by="-load_count",
                     status="", direction="all",
                     destination="", origin="") -> tuple:
        abbreviation = abbreviation.upper()
        cache_key = (
            f"admin:states:detail:{abbreviation}:{page}:{per_page}:"
            f"{search}:{period}:{sort_by}:{status}:{direction}:"
            f"{destination}:{origin}"
        )
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("State detail retrieved", data=cached)

        try:
            state = State.objects.get(abbreviation=abbreviation)
        except State.DoesNotExist:
            return ServiceResponse.not_found("State not found")

        period_q = cls._period_filter(period)

        # get routes where this state is origin or destination (or both)
        if direction == "outbound":
            route_q = Q(origin_state=state)
        elif direction == "inbound":
            route_q = Q(destination_state=state)
        else:
            route_q = Q(origin_state=state) | Q(destination_state=state)

        # specific origin/destination state filter
        if destination:
            route_q &= Q(destination_state__abbreviation__iexact=destination)
        if origin:
            route_q &= Q(origin_state__abbreviation__iexact=origin)

        routes = (
            Route.objects
            .filter(route_q)
            .select_related("origin_state", "destination_state")
        )

        if search:
            search_upper = search.upper()
            routes = routes.filter(
                Q(route_id__icontains=search_upper) |
                Q(origin_state__name__icontains=search) |
                Q(destination_state__name__icontains=search) |
                Q(origin_state__abbreviation__icontains=search_upper) |
                Q(destination_state__abbreviation__icontains=search_upper)
            )

        # annotate with load stats filtered by period and status
        load_filter = period_q
        if status:
            load_filter &= Q(loads__status=status)

        routes = routes.annotate(
            load_count=Count("loads", filter=load_filter),
            total_payout=Sum("loads__payout", filter=load_filter),
            most_expensive=Max("loads__payout", filter=load_filter),
            cheapest=Min("loads__payout", filter=load_filter),
            total_miles=Sum("loads__total_miles", filter=load_filter),
            latest_load=Max("loads__created_at", filter=load_filter),
        ).filter(load_count__gt=0)

        allowed_sorts = {
            "load_count", "-load_count",
            "total_payout", "-total_payout",
            "most_expensive", "-most_expensive",
            "route_id", "-route_id",
            "latest_load", "-latest_load",
        }
        if sort_by not in allowed_sorts:
            sort_by = "-load_count"
        routes = routes.order_by(sort_by)

        total_routes = routes.count()
        offset = (page - 1) * per_page
        routes_page = list(routes[offset:offset + per_page])

        # state-level overview for the filtered set
        if direction == "outbound":
            state_loads_q = Q(route__origin_state=state)
        elif direction == "inbound":
            state_loads_q = Q(route__destination_state=state)
        else:
            state_loads_q = Q(route__origin_state=state) | Q(route__destination_state=state)

        overview_qs = Load.objects.filter(state_loads_q).filter(period_q)
        if status:
            overview_qs = overview_qs.filter(status=status)

        overview_agg = overview_qs.aggregate(
            total_loads=Count("id"),
            total_payout=Sum("payout"),
            most_expensive=Max("payout"),
            cheapest=Min("payout"),
            total_miles=Sum("total_miles"),
        )

        # most expensive load for this state
        from main.services.load_service import LoadService

        most_expensive_load = None
        top_load = (
            overview_qs.select_related("registered_by", "assigned_driver", "route")
            .order_by("-payout")
            .first()
        )
        if top_load:
            most_expensive_load = LoadService._serialize_load_list(top_load)

        # status breakdown
        status_counts = dict(
            overview_qs.values_list("status")
            .annotate(c=Count("id"))
            .values_list("status", "c")
        )

        routes_data = []
        for r in routes_page:
            routes_data.append({
                "route_id": r.route_id,
                "origin_state": {
                    "abbreviation": r.origin_state.abbreviation,
                    "name": r.origin_state.name,
                },
                "destination_state": {
                    "abbreviation": r.destination_state.abbreviation,
                    "name": r.destination_state.name,
                },
                "load_count": r.load_count,
                "total_payout": str(r.total_payout or 0),
                "most_expensive": str(r.most_expensive or 0),
                "cheapest": str(r.cheapest or 0),
                "total_miles": str(r.total_miles or 0),
                "latest_load": r.latest_load.isoformat() if r.latest_load else None,
            })

        data = {
            "state": {
                "abbreviation": state.abbreviation,
                "name": state.name,
            },
            "period": cls._period_label(period),
            "direction": direction,
            "overview": {
                "total_loads": overview_agg["total_loads"] or 0,
                "total_routes": total_routes,
                "total_payout": str(overview_agg["total_payout"] or 0),
                "most_expensive": str(overview_agg["most_expensive"] or 0),
                "cheapest": str(overview_agg["cheapest"] or 0),
                "total_miles": str(overview_agg["total_miles"] or 0),
                "status_breakdown": {
                    "available": status_counts.get("available", 0),
                    "booked": status_counts.get("booked", 0),
                    "in_transit": status_counts.get("in_transit", 0),
                    "delivered": status_counts.get("delivered", 0),
                    "cancelled": status_counts.get("cancelled", 0),
                },
            },
            "most_expensive_load": most_expensive_load,
            "routes": routes_data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_routes,
                "pages": max(1, (total_routes + per_page - 1) // per_page),
            },
        }
        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("State detail retrieved", data=data)

    # ── state analytics (overview for a chosen state) ─────────────────

    @classmethod
    def state_analytics(cls, abbreviation, period="weekly") -> tuple:
        abbreviation = abbreviation.upper()
        cache_key = f"admin:states:analytics:{abbreviation}:{period}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("State analytics", data=cached)

        try:
            state = State.objects.get(abbreviation=abbreviation)
        except State.DoesNotExist:
            return ServiceResponse.not_found("State not found")

        # all loads touching this state
        qs = Load.objects.filter(
            Q(route__origin_state=state) | Q(route__destination_state=state)
        )

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
                unique_routes=Count("route", distinct=True),
                available=Count("id", filter=Q(status="available")),
                booked=Count("id", filter=Q(status="booked")),
                in_transit=Count("id", filter=Q(status="in_transit")),
                delivered=Count("id", filter=Q(status="delivered")),
                cancelled=Count("id", filter=Q(status="cancelled")),
            )
            .order_by("-time_period")
        )

        # overall totals
        overall = qs.aggregate(
            total_loads=Count("id"),
            total_payout=Sum("payout"),
            most_expensive=Max("payout"),
            cheapest=Min("payout"),
            total_miles=Sum("total_miles"),
            unique_routes=Count("route", distinct=True),
        )

        # top routes for this state
        top_routes = list(
            qs.values("route__route_id")
            .annotate(
                load_count=Count("id"),
                total_payout=Sum("payout"),
                most_expensive=Max("payout"),
            )
            .order_by("-load_count")[:10]
        )
        for r in top_routes:
            r["route_id"] = r.pop("route__route_id")
            r["total_payout"] = str(r["total_payout"] or 0)
            r["most_expensive"] = str(r["most_expensive"] or 0)

        # status breakdown
        status_counts = dict(
            qs.values_list("status")
            .annotate(c=Count("id"))
            .values_list("status", "c")
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
                "unique_routes": row["unique_routes"],
                "status_breakdown": {
                    "available": row["available"],
                    "booked": row["booked"],
                    "in_transit": row["in_transit"],
                    "delivered": row["delivered"],
                    "cancelled": row["cancelled"],
                },
            })

        data = {
            "state": {
                "abbreviation": state.abbreviation,
                "name": state.name,
            },
            "period_type": period,
            "overview": {
                "total_loads": overall["total_loads"] or 0,
                "total_payout": str(overall["total_payout"] or 0),
                "most_expensive": str(overall["most_expensive"] or 0),
                "cheapest": str(overall["cheapest"] or 0),
                "total_miles": str(overall["total_miles"] or 0),
                "unique_routes": overall["unique_routes"] or 0,
                "status_breakdown": {
                    "available": status_counts.get("available", 0),
                    "booked": status_counts.get("booked", 0),
                    "in_transit": status_counts.get("in_transit", 0),
                    "delivered": status_counts.get("delivered", 0),
                    "cancelled": status_counts.get("cancelled", 0),
                },
            },
            "top_routes": top_routes,
            "periods": periods_list,
        }

        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("State analytics", data=data)

    # ── cache invalidation ────────────────────────────────────────────

    @classmethod
    def invalidate_state_caches(cls):
        CacheService.delete_pattern("admin:states:*")
