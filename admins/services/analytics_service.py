from datetime import timedelta

from django.db.models import Count, Sum, Avg, Min, Max, Q
from django.db.models.functions import TruncDate, TruncWeek
from django.utils import timezone
from django.utils.dateparse import parse_date

from base.models import Load
from base.services.base_service import ServiceResponse, CacheService


class LoadAnalyticsService:

    CACHE_TTL = 120

    # ── helpers ──────────────────────────────────────────────────────

    @classmethod
    def _parse_period(cls, period_str):
        """Convert period name to timedelta. Returns (start_date, label)."""
        now = timezone.now()
        periods = {
            "24h": (now - timedelta(hours=24), "Last 24 hours"),
            "7d": (now - timedelta(days=7), "Last 7 days"),
            "14d": (now - timedelta(days=14), "Last 14 days"),
            "30d": (now - timedelta(days=30), "Last 30 days"),
            "90d": (now - timedelta(days=90), "Last 90 days"),
            "all": (None, "All time"),
        }
        return periods.get(period_str, periods["7d"])

    @classmethod
    def _date_filter(cls, date_from=None, date_to=None):
        """Build a Q filter from optional date strings or datetime objects."""
        q = Q()
        if date_from:
            if isinstance(date_from, str):
                date_from = parse_date(date_from)
            if date_from:
                q &= Q(created_at__date__gte=date_from)
        if date_to:
            if isinstance(date_to, str):
                date_to = parse_date(date_to)
            if date_to:
                q &= Q(created_at__date__lte=date_to)
        return q

    # ── load frequency (same load_id appearing multiple times) ──────

    @classmethod
    def load_frequency(cls, period="7d", page=1, per_page=20,
                       min_count=2, sort_by="-count") -> tuple:
        """
        Which load_ids appear most often?  Groups by load_id and counts
        occurrences.  Only returns loads that appeared >= min_count times.
        """
        cache_key = f"analytics:freq:{period}:{page}:{per_page}:{min_count}:{sort_by}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Load frequency", data=cached)

        start, label = cls._parse_period(period)
        qs = Load.objects.all()
        if start:
            qs = qs.filter(created_at__gte=start)

        # only loads that have a non-empty load_id
        qs = qs.exclude(load_id="")

        freq = (
            qs.values("load_id")
            .annotate(
                count=Count("id"),
                first_seen=Min("created_at"),
                last_seen=Max("created_at"),
                total_payout=Sum("payout"),
                avg_payout=Avg("payout"),
                avg_miles=Avg("total_miles"),
                statuses=Count("status", distinct=True),
            )
            .filter(count__gte=min_count)
        )

        allowed_sorts = {
            "count", "-count", "load_id", "-load_id",
            "total_payout", "-total_payout", "last_seen", "-last_seen",
        }
        if sort_by not in allowed_sorts:
            sort_by = "-count"
        freq = freq.order_by(sort_by)

        total = freq.count()
        offset = (page - 1) * per_page
        items = list(freq[offset:offset + per_page])

        # enrich each item with status breakdown
        for item in items:
            status_counts = dict(
                Load.objects.filter(load_id=item["load_id"])
                .values_list("status")
                .annotate(c=Count("id"))
                .values_list("status", "c")
            )
            item["status_breakdown"] = status_counts
            # get the most common route for this load_id
            route = (
                Load.objects.filter(load_id=item["load_id"])
                .values("origin_facility", "origin_city", "origin_state",
                        "destination_facility", "destination_city", "destination_state")
                .annotate(c=Count("id"))
                .order_by("-c")
                .first()
            )
            item["primary_route"] = {
                "origin": f"{route['origin_facility']} ({route['origin_city']}, {route['origin_state']})",
                "destination": f"{route['destination_facility']} ({route['destination_city']}, {route['destination_state']})",
            } if route else None
            item["first_seen"] = item["first_seen"].isoformat() if item["first_seen"] else None
            item["last_seen"] = item["last_seen"].isoformat() if item["last_seen"] else None
            item["total_payout"] = str(item["total_payout"] or 0)
            item["avg_payout"] = str(round(item["avg_payout"] or 0, 2))
            item["avg_miles"] = str(round(item["avg_miles"] or 0, 1))

        result = {
            "period": label,
            "loads": items,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": max(1, (total + per_page - 1) // per_page),
            },
        }
        CacheService.set(cache_key, result, cls.CACHE_TTL)
        return ServiceResponse.success("Load frequency", data=result)

    # ── route frequency (most common origin→destination pairs) ──────

    @classmethod
    def route_frequency(cls, period="7d", page=1, per_page=20) -> tuple:
        """Most common routes by origin_facility → destination_facility."""
        cache_key = f"analytics:routes:{period}:{page}:{per_page}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Route frequency", data=cached)

        start, label = cls._parse_period(period)
        qs = Load.objects.all()
        if start:
            qs = qs.filter(created_at__gte=start)

        routes = (
            qs.values(
                "origin_facility", "origin_city", "origin_state",
                "destination_facility", "destination_city", "destination_state",
            )
            .annotate(
                count=Count("id"),
                total_payout=Sum("payout"),
                avg_payout=Avg("payout"),
                avg_miles=Avg("total_miles"),
                unique_load_ids=Count("load_id", distinct=True),
            )
            .order_by("-count")
        )

        total = routes.count()
        offset = (page - 1) * per_page
        items = list(routes[offset:offset + per_page])

        for item in items:
            item["total_payout"] = str(item["total_payout"] or 0)
            item["avg_payout"] = str(round(item["avg_payout"] or 0, 2))
            item["avg_miles"] = str(round(item["avg_miles"] or 0, 1))

        result = {
            "period": label,
            "routes": items,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": max(1, (total + per_page - 1) // per_page),
            },
        }
        CacheService.set(cache_key, result, cls.CACHE_TTL)
        return ServiceResponse.success("Route frequency", data=result)

    # ── trends (loads created over time) ────────────────────────────

    @classmethod
    def trends(cls, period="30d", group_by="day") -> tuple:
        """Load creation counts grouped by day or week."""
        cache_key = f"analytics:trends:{period}:{group_by}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Load trends", data=cached)

        start, label = cls._parse_period(period)
        qs = Load.objects.all()
        if start:
            qs = qs.filter(created_at__gte=start)

        trunc_fn = TruncWeek if group_by == "week" else TruncDate
        trend_data = (
            qs.annotate(period=trunc_fn("created_at"))
            .values("period")
            .annotate(
                count=Count("id"),
                total_payout=Sum("payout"),
                avg_payout=Avg("payout"),
                unique_load_ids=Count("load_id", distinct=True),
                duplicate_count=Count("id") - Count("load_id", distinct=True),
            )
            .order_by("period")
        )

        items = []
        for row in trend_data:
            items.append({
                "date": row["period"].isoformat() if row["period"] else None,
                "count": row["count"],
                "total_payout": str(row["total_payout"] or 0),
                "avg_payout": str(round(row["avg_payout"] or 0, 2)),
                "unique_load_ids": row["unique_load_ids"],
                "duplicate_count": row["duplicate_count"],
            })

        total_loads = sum(i["count"] for i in items)
        total_unique = sum(i["unique_load_ids"] for i in items)

        result = {
            "period": label,
            "group_by": group_by,
            "data": items,
            "summary": {
                "total_loads": total_loads,
                "total_unique_load_ids": total_unique,
                "total_duplicates": total_loads - total_unique,
                "days_covered": len(items),
            },
        }
        CacheService.set(cache_key, result, cls.CACHE_TTL)
        return ServiceResponse.success("Load trends", data=result)

    # ── compare two periods ─────────────────────────────────────────

    @classmethod
    def compare_periods(cls, period_a="7d", period_b="14d") -> tuple:
        """
        Compare two time periods side by side.
        period_a = recent period, period_b = previous period (for comparison).
        """
        cache_key = f"analytics:compare:{period_a}:{period_b}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Period comparison", data=cached)

        def _period_stats(start, end=None):
            qs = Load.objects.all()
            if start:
                qs = qs.filter(created_at__gte=start)
            if end:
                qs = qs.filter(created_at__lt=end)

            total = qs.count()
            if total == 0:
                return {
                    "total_loads": 0,
                    "unique_load_ids": 0,
                    "duplicate_rate": "0.0",
                    "total_payout": "0",
                    "avg_payout": "0",
                    "avg_miles": "0",
                    "status_breakdown": {},
                    "top_load_ids": [],
                    "top_routes": [],
                }

            unique = qs.exclude(load_id="").values("load_id").distinct().count()
            agg = qs.aggregate(
                total_payout=Sum("payout"),
                avg_payout=Avg("payout"),
                avg_miles=Avg("total_miles"),
            )
            statuses = dict(
                qs.values_list("status")
                .annotate(c=Count("id"))
                .values_list("status", "c")
            )
            top_ids = list(
                qs.exclude(load_id="")
                .values("load_id")
                .annotate(count=Count("id"))
                .filter(count__gte=2)
                .order_by("-count")[:5]
            )
            top_routes = list(
                qs.values("origin_facility", "destination_facility")
                .annotate(count=Count("id"))
                .order_by("-count")[:5]
            )

            dup_rate = 0
            if total > 0 and unique > 0:
                dup_rate = round((total - unique) / total * 100, 1)

            return {
                "total_loads": total,
                "unique_load_ids": unique,
                "duplicate_rate": str(dup_rate),
                "total_payout": str(agg["total_payout"] or 0),
                "avg_payout": str(round(agg["avg_payout"] or 0, 2)),
                "avg_miles": str(round(agg["avg_miles"] or 0, 1)),
                "status_breakdown": statuses,
                "top_load_ids": top_ids,
                "top_routes": top_routes,
            }

        start_a, label_a = cls._parse_period(period_a)
        start_b, label_b = cls._parse_period(period_b)

        stats_a = _period_stats(start_a)
        stats_b = _period_stats(start_b, end=start_a)

        # calculate changes
        changes = {}
        for key in ("total_loads", "unique_load_ids"):
            val_a = stats_a[key]
            val_b = stats_b[key]
            if val_b > 0:
                pct = round((val_a - val_b) / val_b * 100, 1)
            elif val_a > 0:
                pct = 100.0
            else:
                pct = 0.0
            changes[key] = {"change": val_a - val_b, "change_pct": str(pct)}

        result = {
            "period_a": {"label": label_a, "stats": stats_a},
            "period_b": {"label": label_b, "stats": stats_b},
            "changes": changes,
        }
        CacheService.set(cache_key, result, cls.CACHE_TTL)
        return ServiceResponse.success("Period comparison", data=result)

    # ── overview dashboard ──────────────────────────────────────────

    @classmethod
    def overview(cls) -> tuple:
        """High-level analytics dashboard."""
        cache_key = "analytics:overview"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Analytics overview", data=cached)

        now = timezone.now()

        # totals
        total = Load.objects.count()
        total_unique = Load.objects.exclude(load_id="").values("load_id").distinct().count()

        # this week vs last week
        week_start = now - timedelta(days=7)
        prev_week_start = now - timedelta(days=14)
        this_week = Load.objects.filter(created_at__gte=week_start).count()
        last_week = Load.objects.filter(
            created_at__gte=prev_week_start, created_at__lt=week_start
        ).count()

        # duplicates this week (same load_id appearing 2+ times)
        duplicates_this_week = (
            Load.objects.filter(created_at__gte=week_start)
            .exclude(load_id="")
            .values("load_id")
            .annotate(count=Count("id"))
            .filter(count__gte=2)
            .count()
        )

        # top 10 most repeated loads (all time)
        top_repeated = list(
            Load.objects.exclude(load_id="")
            .values("load_id")
            .annotate(
                count=Count("id"),
                total_payout=Sum("payout"),
                last_seen=Max("created_at"),
            )
            .filter(count__gte=2)
            .order_by("-count")[:10]
        )
        for item in top_repeated:
            item["total_payout"] = str(item["total_payout"] or 0)
            item["last_seen"] = item["last_seen"].isoformat() if item["last_seen"] else None

        # top 5 routes this week
        top_routes_week = list(
            Load.objects.filter(created_at__gte=week_start)
            .values("origin_facility", "origin_city", "origin_state",
                    "destination_facility", "destination_city", "destination_state")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        week_change = 0
        if last_week > 0:
            week_change = round((this_week - last_week) / last_week * 100, 1)

        data = {
            "total_loads": total,
            "total_unique_load_ids": total_unique,
            "total_duplicates": total - total_unique if total > total_unique else 0,
            "this_week": {
                "loads": this_week,
                "change_vs_last_week": str(week_change),
                "duplicates": duplicates_this_week,
            },
            "last_week": {
                "loads": last_week,
            },
            "top_repeated_loads": top_repeated,
            "top_routes_this_week": top_routes_week,
        }

        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("Analytics overview", data=data)
