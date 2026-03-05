from django.core.management.base import BaseCommand

from base.models import Permission, Role, RolePermission


PERMISSIONS = {
    "users": [
        ("users.view", "View users"),
        ("users.create", "Create users"),
        ("users.update", "Update users"),
        ("users.delete", "Delete users"),
    ],
    "roles": [
        ("roles.view", "View roles"),
        ("roles.create", "Create roles"),
        ("roles.update", "Update roles"),
        ("roles.delete", "Delete roles"),
    ],
    "loads": [
        ("loads.view", "View loads"),
        ("loads.create", "Create loads"),
        ("loads.update", "Update loads"),
        ("loads.delete", "Delete loads"),
        ("loads.assign", "Assign loads"),
    ],
    "facilities": [
        ("facilities.view", "View facilities"),
        ("facilities.create", "Create facilities"),
        ("facilities.update", "Update facilities"),
        ("facilities.delete", "Delete facilities"),
    ],
    "reports": [
        ("reports.view", "View reports"),
        ("reports.export", "Export reports"),
    ],
    "analytics": [
        ("analytics.view", "View analytics"),
        ("analytics.compare", "Compare analytics periods"),
    ],
}

ROLES = [
    {
        "name": "Admin",
        "slug": "admin",
        "description": "Full system access",
        "is_default": False,
        "permissions": "__all__",
    },
    {
        "name": "Manager",
        "slug": "manager",
        "description": "Manage loads, users, and facilities",
        "is_default": False,
        "permissions": [
            "users.view", "loads.view", "loads.create", "loads.update",
            "loads.assign", "facilities.view", "reports.view", "reports.export",
            "analytics.view", "analytics.compare",
        ],
    },
    {
        "name": "Dispatcher",
        "slug": "dispatcher",
        "description": "Manage and assign loads",
        "is_default": False,
        "permissions": [
            "loads.view", "loads.create", "loads.update", "loads.assign",
            "facilities.view",
        ],
    },
    {
        "name": "Driver",
        "slug": "driver",
        "description": "View assigned loads",
        "is_default": True,
        "permissions": ["loads.view", "facilities.view"],
    },
]


class Command(BaseCommand):
    help = "Seed permissions and roles"

    def handle(self, *args, **options):
        created_perms = 0
        for module, perms in PERMISSIONS.items():
            for codename, name in perms:
                _, created = Permission.objects.get_or_create(
                    codename=codename,
                    defaults={"name": name, "module": module},
                )
                if created:
                    created_perms += 1

        self.stdout.write(f"Permissions: {created_perms} created, {Permission.objects.count()} total")

        all_perms = list(Permission.objects.all())
        all_codenames = {p.codename: p for p in all_perms}

        created_roles = 0
        for role_data in ROLES:
            role, created = Role.objects.get_or_create(
                slug=role_data["slug"],
                defaults={
                    "name": role_data["name"],
                    "description": role_data["description"],
                    "is_default": role_data["is_default"],
                },
            )
            if created:
                created_roles += 1

            if role_data["permissions"] == "__all__":
                target_perms = all_perms
            else:
                target_perms = [all_codenames[c] for c in role_data["permissions"] if c in all_codenames]

            existing = set(
                RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)
            )
            new_rps = [
                RolePermission(role=role, permission=p)
                for p in target_perms if p.pk not in existing
            ]
            if new_rps:
                RolePermission.objects.bulk_create(new_rps)

            self.stdout.write(f"  {role.name}: {role.permissions.count()} permissions")

        self.stdout.write(self.style.SUCCESS(
            f"Done. {created_roles} roles created, {Role.objects.count()} total"
        ))
