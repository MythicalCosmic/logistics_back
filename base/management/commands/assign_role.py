from django.core.management.base import BaseCommand, CommandError

from base.models import User, Role, UserRole


class Command(BaseCommand):
    help = "Assign a role to a user: manage.py assign_role <email> <role_slug>"

    def add_arguments(self, parser):
        parser.add_argument("email", type=str)
        parser.add_argument("role_slug", type=str)

    def handle(self, *args, **options):
        email = options["email"]
        slug = options["role_slug"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"User '{email}' not found")

        try:
            role = Role.objects.get(slug=slug)
        except Role.DoesNotExist:
            available = ", ".join(Role.objects.values_list("slug", flat=True))
            raise CommandError(f"Role '{slug}' not found. Available: {available}")

        _, created = UserRole.objects.get_or_create(user=user, role=role)

        if created:
            self.stdout.write(self.style.SUCCESS(f"Assigned '{role.name}' to {user.email}"))
        else:
            self.stdout.write(self.style.WARNING(f"{user.email} already has '{role.name}'"))

        roles = list(user.roles.values_list("slug", flat=True))
        self.stdout.write(f"Current roles: {', '.join(roles)}")
