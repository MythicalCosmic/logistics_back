from django.core.management.base import BaseCommand, CommandError

from base.models import User, Role, UserRole


class Command(BaseCommand):
    help = "Create an admin user or promote existing: manage.py create_admin <email> [--password <pw>]"

    def add_arguments(self, parser):
        parser.add_argument("email", type=str)
        parser.add_argument("--password", type=str, default=None)
        parser.add_argument("--first-name", type=str, default="Admin")
        parser.add_argument("--last-name", type=str, default="User")

    def handle(self, *args, **options):
        email = options["email"]
        password = options["password"]

        try:
            admin_role = Role.objects.get(slug="admin")
        except Role.DoesNotExist:
            raise CommandError("Admin role not found. Run 'python manage.py seed_permissions' first")

        user = User.objects.filter(email=email).first()

        if user:
            self.stdout.write(f"Found existing user: {user.email}")
            if password:
                user.set_password(password)
                user.save(update_fields=["password"])
                self.stdout.write("Password updated")
        else:
            if not password:
                raise CommandError("--password is required for new users")
            user = User(
                email=email,
                first_name=options["first_name"],
                last_name=options["last_name"],
            )
            user.set_password(password)
            user.is_active = True
            user.save()
            self.stdout.write(f"Created user: {user.email}")

        _, created = UserRole.objects.get_or_create(user=user, role=admin_role)
        if created:
            self.stdout.write(self.style.SUCCESS(f"Admin role assigned to {user.email}"))
        else:
            self.stdout.write(f"{user.email} is already admin")

        roles = list(user.roles.values_list("slug", flat=True))
        self.stdout.write(self.style.SUCCESS(f"Done. Roles: {', '.join(roles)}"))
