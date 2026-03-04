from django.db import transaction
from django.db.models import Count

from base.models import Role, Permission, RolePermission, UserRole
from base.services.base_service import ServiceResponse
from base.services.role_permission_service import RolePermissionService


class AdminRoleService:

    @classmethod
    def list_roles(cls) -> tuple:
        roles = Role.objects.annotate(
            user_count=Count("users", distinct=True),
            permission_count=Count("permissions", distinct=True),
        )

        data = []
        for role in roles:
            r = cls._serialize_role(role)
            r["user_count"] = role.user_count
            r["permission_count"] = role.permission_count
            data.append(r)

        return ServiceResponse.success("Roles retrieved", data=data)

    @classmethod
    def get_role(cls, role_id: int) -> tuple:
        try:
            role = Role.objects.prefetch_related("permissions").get(pk=role_id)
        except Role.DoesNotExist:
            return ServiceResponse.not_found("Role not found")

        data = cls._serialize_role(role)
        data["permissions"] = list(
            role.permissions.values("id", "codename", "name", "module")
        )
        data["user_count"] = UserRole.objects.filter(role=role).count()
        data["users"] = list(
            role.users.values("id", "email", "first_name", "last_name", "is_active")[:50]
        )

        return ServiceResponse.success("Role retrieved", data=data)

    @classmethod
    @transaction.atomic
    def create_role(cls, name: str, slug: str, description: str = "") -> tuple:
        if Role.objects.filter(slug=slug).exists():
            return ServiceResponse.error("Role slug already exists")

        if Role.objects.filter(name=name).exists():
            return ServiceResponse.error("Role name already exists")

        role = Role.objects.create(
            name=name,
            slug=slug,
            description=description,
        )

        return ServiceResponse.success(
            "Role created successfully",
            data=cls._serialize_role(role),
            status=201,
        )

    @classmethod
    @transaction.atomic
    def update_role(cls, role_id: int, **fields) -> tuple:
        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return ServiceResponse.not_found("Role not found")

        if "slug" in fields and fields["slug"] != role.slug:
            if Role.objects.filter(slug=fields["slug"]).exclude(pk=role_id).exists():
                return ServiceResponse.error("Role slug already exists")

        if "name" in fields and fields["name"] != role.name:
            if Role.objects.filter(name=fields["name"]).exclude(pk=role_id).exists():
                return ServiceResponse.error("Role name already exists")

        update_fields = []
        for field, value in fields.items():
            setattr(role, field, value)
            update_fields.append(field)

        role.save(update_fields=update_fields)

        return ServiceResponse.success(
            "Role updated successfully",
            data=cls._serialize_role(role),
        )

    @classmethod
    @transaction.atomic
    def delete_role(cls, role_id: int) -> tuple:
        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return ServiceResponse.not_found("Role not found")

        if role.is_default:
            return ServiceResponse.error("Cannot delete a default role")

        user_count = UserRole.objects.filter(role=role).count()
        if user_count > 0:
            return ServiceResponse.error(
                f"Cannot delete role with {user_count} assigned users. Remove users first"
            )

        role.delete()

        return ServiceResponse.success("Role deleted successfully")

    @classmethod
    def assign_permission(cls, role_id: int, permission_id: int) -> tuple:
        return RolePermissionService.assign_permission_to_role(role_id, permission_id)

    @classmethod
    def remove_permission(cls, role_id: int, permission_id: int) -> tuple:
        return RolePermissionService.remove_permission_from_role(role_id, permission_id)

    @classmethod
    def bulk_assign_permissions(cls, role_id: int, permission_ids: list) -> tuple:
        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return ServiceResponse.not_found("Role not found")

        permissions = Permission.objects.filter(pk__in=permission_ids)
        if permissions.count() != len(permission_ids):
            return ServiceResponse.error("One or more permissions not found")

        existing = set(
            RolePermission.objects.filter(role=role, permission_id__in=permission_ids)
            .values_list("permission_id", flat=True)
        )

        new_rps = [
            RolePermission(role=role, permission_id=pid)
            for pid in permission_ids if pid not in existing
        ]

        if new_rps:
            RolePermission.objects.bulk_create(new_rps)
            RolePermissionService._invalidate_role_users(role_id)

        return ServiceResponse.success(
            f"Assigned {len(new_rps)} permissions, {len(existing)} already existed",
            data={"assigned": len(new_rps), "skipped": len(existing)},
        )

    @classmethod
    def list_permissions(cls) -> tuple:
        permissions = Permission.objects.all()
        grouped = {}
        for p in permissions:
            if p.module not in grouped:
                grouped[p.module] = []
            grouped[p.module].append({
                "id": p.pk,
                "codename": p.codename,
                "name": p.name,
            })

        return ServiceResponse.success("Permissions retrieved", data={
            "permissions": list(permissions.values("id", "codename", "name", "module")),
            "grouped": grouped,
            "total": permissions.count(),
        })

    @classmethod
    def stats(cls) -> tuple:
        roles = Role.objects.annotate(
            user_count=Count("users", distinct=True),
            permission_count=Count("permissions", distinct=True),
        ).values("id", "name", "slug", "user_count", "permission_count")

        total_permissions = Permission.objects.count()
        total_roles = Role.objects.count()

        return ServiceResponse.success("Role statistics", data={
            "total_roles": total_roles,
            "total_permissions": total_permissions,
            "roles": list(roles),
        })

    @classmethod
    def _serialize_role(cls, role: Role) -> dict:
        return {
            "id": role.pk,
            "name": role.name,
            "slug": role.slug,
            "description": role.description,
            "is_default": role.is_default,
            "created_at": role.created_at.isoformat() if role.created_at else None,
            "updated_at": role.updated_at.isoformat() if role.updated_at else None,
        }
