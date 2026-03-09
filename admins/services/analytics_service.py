from datetime import timedelta

from django.db.models import Count, Sum, Min, Max, Q
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

    # ── load frequency (same load_id / route appearing multiple times) ──

    @classmethod
    def load_frequency(cls, period="7d", page=1, per_page=20,
                       min_count=2, sort_by="-count") -> tuple:
        cache_key = f"analytics:freq:{period}:{page}:{per_page}:{min_count}:{sort_by}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Load frequency", data=cached)

        start, label = cls._parse_period(period)
        qs = Load.objects.all()
        if start:
            qs = qs.filter(created_at__gte=start)

        qs = qs.exclude(load_id="")

        freq = (
            qs.values("load_id")
            .annotate(
                count=Count("id"),
                first_seen=Min("created_at"),
                last_seen=Max("created_at"),
                total_payout=Sum("payout"),
                most_expensive=Max("payout"),
                cheapest=Min("payout"),
                total_miles=Sum("total_miles"),
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

        for item in items:
            status_counts = dict(
                Load.objects.filter(load_id=item["load_id"])
                .values_list("status")
                .annotate(c=Count("id"))
                .values_list("status", "c")
            )
            item["status_breakdown"] = status_counts
            item["first_seen"] = item["first_seen"].isoformat() if item["first_seen"] else None
            item["last_seen"] = item["last_seen"].isoformat() if item["last_seen"] else None
            item["total_payout"] = str(item["total_payout"] or 0)
            item["most_expensive"] = str(item["most_expensive"] or 0)
            item["cheapest"] = str(item["cheapest"] or 0)
            item["total_miles"] = str(item["total_miles"] or 0)

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

    # ── route frequency (most common origin→destination state pairs) ──

    @classmethod
    def route_frequency(cls, period="7d", page=1, per_page=20) -> tuple:
        cache_key = f"analytics:routes:{period}:{page}:{per_page}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Route frequency", data=cached)

        start, label = cls._parse_period(period)
        qs = Load.objects.exclude(load_id="")
        if start:
            qs = qs.filter(created_at__gte=start)

        routes = (
            qs.values("load_id")
            .annotate(
                count=Count("id"),
                total_payout=Sum("payout"),
                most_expensive=Max("payout"),
                cheapest=Min("payout"),
                total_miles=Sum("total_miles"),
            )
            .order_by("-count")
        )

        total = routes.count()
        offset = (page - 1) * per_page
        items = list(routes[offset:offset + per_page])

        for item in items:
            item["total_payout"] = str(item["total_payout"] or 0)
            item["most_expensive"] = str(item["most_expensive"] or 0)
            item["cheapest"] = str(item["cheapest"] or 0)
            item["total_miles"] = str(item["total_miles"] or 0)

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
                most_expensive=Max("payout"),
                cheapest=Min("payout"),
                total_miles=Sum("total_miles"),
                unique_routes=Count("load_id", distinct=True),
            )
            .order_by("period")
        )

        items = []
        for row in trend_data:
            items.append({
                "date": row["period"].isoformat() if row["period"] else None,
                "count": row["count"],
                "total_payout": str(row["total_payout"] or 0),
                "most_expensive": str(row["most_expensive"] or 0),
                "cheapest": str(row["cheapest"] or 0),
                "total_miles": str(row["total_miles"] or 0),
                "unique_routes": row["unique_routes"],
            })

        total_loads = sum(i["count"] for i in items)
        total_routes = sum(i["unique_routes"] for i in items)

        result = {
            "period": label,
            "group_by": group_by,
            "data": items,
            "summary": {
                "total_loads": total_loads,
                "total_unique_routes": total_routes,
                "days_covered": len(items),
            },
        }
        CacheService.set(cache_key, result, cls.CACHE_TTL)
        return ServiceResponse.success("Load trends", data=result)

    # ── compare two periods ─────────────────────────────────────────

    @classmethod
    def compare_periods(cls, period_a="7d", period_b="14d") -> tuple:
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
                    "unique_routes": 0,
                    "total_payout": "0",
                    "most_expensive": "0",
                    "cheapest": "0",
                    "total_miles": "0",
                    "status_breakdown": {},
                    "top_routes": [],
                }

            unique = qs.exclude(load_id="").values("load_id").distinct().count()
            agg = qs.aggregate(
                total_payout=Sum("payout"),
                most_expensive=Max("payout"),
                cheapest=Min("payout"),
                total_miles=Sum("total_miles"),
            )
            statuses = dict(
                qs.values_list("status")
                .annotate(c=Count("id"))
                .values_list("status", "c")
            )
            top_routes = list(
                qs.exclude(load_id="")
                .values("load_id")
                .annotate(
                    count=Count("id"),
                    total_payout=Sum("payout"),
                    most_expensive=Max("payout"),
                    cheapest=Min("payout"),
                )
                .order_by("-count")[:10]
            )
            for r in top_routes:
                r["total_payout"] = str(r["total_payout"] or 0)
                r["most_expensive"] = str(r["most_expensive"] or 0)
                r["cheapest"] = str(r["cheapest"] or 0)

            return {
                "total_loads": total,
                "unique_routes": unique,
                "total_payout": str(agg["total_payout"] or 0),
                "most_expensive": str(agg["most_expensive"] or 0),
                "cheapest": str(agg["cheapest"] or 0),
                "total_miles": str(agg["total_miles"] or 0),
                "status_breakdown": statuses,
                "top_routes": top_routes,
            }

        start_a, label_a = cls._parse_period(period_a)
        start_b, label_b = cls._parse_period(period_b)

        stats_a = _period_stats(start_a)
        stats_b = _period_stats(start_b, end=start_a)

        changes = {}
        for key in ("total_loads", "unique_routes"):
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
        cache_key = "analytics:overview"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Analytics overview", data=cached)

        now = timezone.now()

        total = Load.objects.count()
        total_unique_routes = Load.objects.exclude(load_id="").values("load_id").distinct().count()

        # this week vs last week
        week_start = now - timedelta(days=7)
        prev_week_start = now - timedelta(days=14)

        this_week_qs = Load.objects.filter(created_at__gte=week_start)
        last_week_qs = Load.objects.filter(
            created_at__gte=prev_week_start, created_at__lt=week_start
        )

        this_week_count = this_week_qs.count()
        last_week_count = last_week_qs.count()

        this_week_agg = this_week_qs.aggregate(
            total_payout=Sum("payout"),
            most_expensive=Max("payout"),
            cheapest=Min("payout"),
            total_miles=Sum("total_miles"),
        )

        # top 10 routes (all time) by load count
        top_routes = list(
            Load.objects.exclude(load_id="")
            .values("load_id")
            .annotate(
                count=Count("id"),
                total_payout=Sum("payout"),
                most_expensive=Max("payout"),
                cheapest=Min("payout"),
                total_miles=Sum("total_miles"),
                last_seen=Max("created_at"),
            )
            .order_by("-count")[:10]
        )
        for item in top_routes:
            item["total_payout"] = str(item["total_payout"] or 0)
            item["most_expensive"] = str(item["most_expensive"] or 0)
            item["cheapest"] = str(item["cheapest"] or 0)
            item["total_miles"] = str(item["total_miles"] or 0)
            item["last_seen"] = item["last_seen"].isoformat() if item["last_seen"] else None

        # top routes this week
        top_routes_week = list(
            this_week_qs.exclude(load_id="")
            .values("load_id")
            .annotate(
                count=Count("id"),
                total_payout=Sum("payout"),
                most_expensive=Max("payout"),
                cheapest=Min("payout"),
            )
            .order_by("-count")[:5]
        )
        for r in top_routes_week:
            r["total_payout"] = str(r["total_payout"] or 0)
            r["most_expensive"] = str(r["most_expensive"] or 0)
            r["cheapest"] = str(r["cheapest"] or 0)

        week_change = 0
        if last_week_count > 0:
            week_change = round((this_week_count - last_week_count) / last_week_count * 100, 1)

        data = {
            "total_loads": total,
            "total_unique_routes": total_unique_routes,
            "this_week": {
                "loads": this_week_count,
                "change_vs_last_week": str(week_change),
                "total_payout": str(this_week_agg["total_payout"] or 0),
                "most_expensive": str(this_week_agg["most_expensive"] or 0),
                "cheapest": str(this_week_agg["cheapest"] or 0),
                "total_miles": str(this_week_agg["total_miles"] or 0),
            },
            "last_week": {
                "loads": last_week_count,
            },
            "top_routes": top_routes,
            "top_routes_this_week": top_routes_week,
        }

        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("Analytics overview", data=data)
