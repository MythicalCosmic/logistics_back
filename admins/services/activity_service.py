from django.db.models import Q

from base.models import ActivityLog
from base.services.base_service import ServiceResponse, CacheService


class AdminActivityService:

    CACHE_TTL = 60  # 1 minute for activity logs (they change frequently)

    @classmethod
    def list_logs(cls, page=1, per_page=20, user_id=None, action="",
                  load_id=None, date_from=None, date_to=None, search="") -> tuple:
        cache_key = f"activity:list:{page}:{per_page}:{user_id}:{action}:{load_id}:{date_from}:{date_to}:{search}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Activity logs retrieved", data=cached)

        qs = ActivityLog.objects.select_related("user", "load").all()

        if user_id:
            qs = qs.filter(user_id=user_id)
        if action:
            qs = qs.filter(action=action)
        if load_id:
            qs = qs.filter(load_id=load_id)
        if date_from:
            qs = qs.filter(created_at__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__lte=date_to)
        if search:
            qs = qs.filter(
                Q(action__icontains=search) |
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(ip_address__icontains=search)
            )

        total = qs.count()
        offset = (page - 1) * per_page
        logs = qs[offset:offset + per_page]

        result_data = {
            "logs": [cls._serialize(log) for log in logs],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": max(1, (total + per_page - 1) // per_page),
            },
        }
        CacheService.set(cache_key, result_data, cls.CACHE_TTL)
        return ServiceResponse.success("Activity logs retrieved", data=result_data)

    @classmethod
    def get_log(cls, log_id: int) -> tuple:
        cache_key = f"activity:detail:{log_id}"
        cached = CacheService.get(cache_key)
        if cached:
            return ServiceResponse.success("Activity log retrieved", data=cached)

        try:
            log = ActivityLog.objects.select_related("user", "load").get(pk=log_id)
        except ActivityLog.DoesNotExist:
            return ServiceResponse.not_found("Activity log not found")

        data = cls._serialize(log)
        CacheService.set(cache_key, data, cls.CACHE_TTL)
        return ServiceResponse.success("Activity log retrieved", data=data)

    @classmethod
    def _serialize(cls, log: ActivityLog) -> dict:
        return {
            "id": log.pk,
            "user": {
                "id": log.user.pk,
                "email": log.user.email,
                "full_name": log.user.full_name,
            },
            "load": {
                "id": log.load.pk,
                "load_id": log.load.load_id,
            } if log.load else None,
            "action": log.action,
            "details": log.details,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
