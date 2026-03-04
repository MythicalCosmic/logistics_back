from django.db import transaction
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from base.models import User, Role, Session, UserRole
from base.services.base_service import ServiceResponse, CacheService
from base.services.role_permission_service import RolePermissionService


class AdminUserService:

    @classmethod
    def list_users(cls, page: int = 1, per_page: int = 20,
                   search: str = "", is_active: bool = None,
                   role_slug: str = "", sort_by: str = "-created_at") -> tuple:
        qs = User.objects.all()

        if search:
            qs = qs.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(phone__icontains=search)
            )

        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        if role_slug:
            qs = qs.filter(roles__slug=role_slug).distinct()

        allowed_sorts = {
            "created_at", "-created_at", "email", "-email",
            "first_name", "-first_name", "last_login_at", "-last_login_at",
            "id", "-id",
        }
        if sort_by not in allowed_sorts:
            sort_by = "-created_at"

        qs = qs.order_by(sort_by)
        total = qs.count()
        offset = (page - 1) * per_page
        users = qs.prefetch_related("roles")[offset:offset + per_page]

        return ServiceResponse.success("Users retrieved", data={
            "users": [cls._serialize_user_list(u) for u in users],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": max(1, (total + per_page - 1) // per_page),
            },
        })

    @classmethod
    def get_user(cls, user_id: int) -> tuple:
        try:
            user = User.objects.prefetch_related("roles", "roles__permissions").get(pk=user_id)
        except User.DoesNotExist:
            return ServiceResponse.not_found("User not found")

        data = cls._serialize_user_detail(user)

        return ServiceResponse.success("User retrieved", data=data)

    @classmethod
    @transaction.atomic
    def create_user(cls, email: str, first_name: str, last_name: str,
                    password: str, phone: str = "", role_id: int = None) -> tuple:
        if User.objects.filter(email=email).exists():
            return ServiceResponse.error("Email already exists")

        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
        )
        user.set_password(password)
        user.save()

        if role_id:
            try:
                role = Role.objects.get(pk=role_id)
                UserRole.objects.create(user=user, role=role)
            except Role.DoesNotExist:
                pass

        default_roles = Role.objects.filter(is_default=True)
        for role in default_roles:
            UserRole.objects.get_or_create(user=user, role=role)

        return ServiceResponse.success(
            "User created successfully",
            data=cls._serialize_user_detail(user),
            status=201,
        )

    @classmethod
    @transaction.atomic
    def update_user(cls, user_id: int, **fields) -> tuple:
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return ServiceResponse.not_found("User not found")

        if "email" in fields and fields["email"] != user.email:
            if User.objects.filter(email=fields["email"]).exclude(pk=user_id).exists():
                return ServiceResponse.error("Email already exists")

        update_fields = []
        for field, value in fields.items():
            setattr(user, field, value)
            update_fields.append(field)

        user.save(update_fields=update_fields)
        CacheService.delete(f"user:{user_id}")

        return ServiceResponse.success(
            "User updated successfully",
            data=cls._serialize_user_detail(user),
        )

    @classmethod
    @transaction.atomic
    def delete_user(cls, user_id: int, admin_id: int = None, force: bool = False) -> tuple:
        if admin_id and user_id == admin_id and not force:
            return ServiceResponse.error("Cannot deactivate your own account without force=true")

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return ServiceResponse.not_found("User not found")

        if not user.is_active:
            return ServiceResponse.error("User is already deactivated")

        user.is_active = False
        user.save(update_fields=["is_active"])

        RolePermissionService.nuke_user_sessions(user_id)

        return ServiceResponse.success("User deactivated successfully")

    @classmethod
    @transaction.atomic
    def toggle_active(cls, user_id: int, admin_id: int = None, force: bool = False) -> tuple:
        if admin_id and user_id == admin_id and not force:
            return ServiceResponse.error("Cannot toggle your own account without force=true")

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return ServiceResponse.not_found("User not found")

        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])

        if not user.is_active:
            RolePermissionService.nuke_user_sessions(user_id)
        else:
            RolePermissionService.invalidate_user_cache(user_id)

        status_text = "activated" if user.is_active else "deactivated"
        return ServiceResponse.success(
            f"User {status_text} successfully",
            data={"id": user.pk, "is_active": user.is_active},
        )

    @classmethod
    @transaction.atomic
    def change_password(cls, user_id: int, new_password: str,
                        admin_id: int = None, force: bool = False) -> tuple:
        if admin_id and user_id == admin_id and not force:
            return ServiceResponse.error("Cannot change your own password from admin panel without force=true")

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return ServiceResponse.not_found("User not found")

        user.set_password(new_password)
        user.save(update_fields=["password"])

        RolePermissionService.nuke_user_sessions(user_id)

        return ServiceResponse.success("Password changed and all sessions terminated")

    @classmethod
    def force_logout(cls, user_id: int, admin_id: int = None, force: bool = False) -> tuple:
        if admin_id and user_id == admin_id and not force:
            return ServiceResponse.error("Cannot force logout yourself without force=true")

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return ServiceResponse.not_found("User not found")

        count = Session.objects.filter(
            user=user, is_active=True, expires_at__gt=timezone.now()
        ).count()

        RolePermissionService.nuke_user_sessions(user_id)

        return ServiceResponse.success(
            f"Terminated {count} active sessions",
            data={"sessions_terminated": count},
        )

    @classmethod
    def get_user_sessions(cls, user_id: int) -> tuple:
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return ServiceResponse.not_found("User not found")

        sessions = Session.objects.filter(
            user=user, is_active=True, expires_at__gt=timezone.now()
        ).values("key", "ip_address", "device", "user_agent", "last_activity_at", "created_at")

        data = []
        for s in sessions:
            data.append({
                "key": s["key"][:12] + "...",
                "ip_address": s["ip_address"],
                "device": s["device"],
                "user_agent": s["user_agent"][:100] if s["user_agent"] else "",
                "last_activity": s["last_activity_at"].isoformat() if s["last_activity_at"] else None,
                "created_at": s["created_at"].isoformat() if s["created_at"] else None,
            })

        return ServiceResponse.success("User sessions", data=data)

    @classmethod
    def assign_role(cls, user_id: int, role_id: int, assigned_by=None) -> tuple:
        return RolePermissionService.assign_role_to_user(user_id, role_id, assigned_by)

    @classmethod
    def remove_role(cls, user_id: int, role_id: int) -> tuple:
        return RolePermissionService.remove_role_from_user(user_id, role_id)

    @classmethod
    def stats(cls) -> tuple:
        now = timezone.now()
        total = User.objects.count()
        active = User.objects.filter(is_active=True).count()
        inactive = total - active

        last_24h = User.objects.filter(created_at__gte=now - timedelta(hours=24)).count()
        last_7d = User.objects.filter(created_at__gte=now - timedelta(days=7)).count()
        last_30d = User.objects.filter(created_at__gte=now - timedelta(days=30)).count()

        active_sessions = Session.objects.filter(
            is_active=True, expires_at__gt=now
        ).count()

        logged_in_24h = User.objects.filter(
            last_login_at__gte=now - timedelta(hours=24)
        ).count()

        roles_breakdown = list(
            Role.objects.annotate(user_count=Count("users")).values("name", "slug", "user_count")
        )

        return ServiceResponse.success("User statistics", data={
            "total_users": total,
            "active_users": active,
            "inactive_users": inactive,
            "new_last_24h": last_24h,
            "new_last_7d": last_7d,
            "new_last_30d": last_30d,
            "active_sessions": active_sessions,
            "logged_in_last_24h": logged_in_24h,
            "roles_breakdown": roles_breakdown,
        })

    @classmethod
    def _serialize_user_list(cls, user: User) -> dict:
        return {
            "id": user.pk,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone": user.phone,
            "is_active": user.is_active,
            "roles": list(user.roles.values_list("slug", flat=True)),
            "last_login": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }

    @classmethod
    def _serialize_user_detail(cls, user: User) -> dict:
        return {
            "id": user.pk,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone": user.phone,
            "is_active": user.is_active,
            "email_verified": user.email_verified_at is not None,
            "last_login": user.last_login_at.isoformat() if user.last_login_at else None,
            "last_login_ip": user.last_login_ip,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "roles": list(user.roles.values("id", "name", "slug")),
            "permissions": list(user.get_permissions()),
        }
