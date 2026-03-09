import hashlib
import uuid
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone


class Permission(models.Model):
    codename = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    module = models.CharField(max_length=50, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "permissions"
        ordering = ["module", "codename"]

    def __str__(self):
        return self.codename


class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, db_index=True)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, through="RolePermission", related_name="roles")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "roles"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def has_permission(self, codename):
        return self.permissions.filter(codename=codename).exists()


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "role_permissions"
        unique_together = ["role", "permission"]


class User(models.Model):
    email = models.EmailField(max_length=255, unique=True, db_index=True)
    password = models.CharField(max_length=255)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.CharField(max_length=500, blank=True)
    roles = models.ManyToManyField(
        Role, through="UserRole", through_fields=("user", "role"), related_name="users"
    )
    is_active = models.BooleanField(default=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def has_role(self, slug):
        return self.roles.filter(slug=slug).exists()

    def has_any_role(self, slugs):
        return self.roles.filter(slug__in=slugs).exists()

    def has_permission(self, codename):
        return Permission.objects.filter(
            rolepermission__role__userrole__user=self,
            codename=codename,
        ).exists()

    def has_any_permission(self, codenames):
        return Permission.objects.filter(
            rolepermission__role__userrole__user=self,
            codename__in=codenames,
        ).exists()

    def get_permissions(self):
        return Permission.objects.filter(
            rolepermission__role__userrole__user=self
        ).distinct().values_list("codename", flat=True)

    def get_roles(self):
        return self.roles.values_list("slug", flat=True)

    def assign_role(self, slug):
        role = Role.objects.get(slug=slug)
        UserRole.objects.get_or_create(user=self, role=role)

    def remove_role(self, slug):
        UserRole.objects.filter(user=self, role__slug=slug).delete()


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="role_assignments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_roles"
        unique_together = ["user", "role"]


class Session(models.Model):
    key = models.CharField(max_length=64, primary_key=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device = models.CharField(max_length=200, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sessions"
        ordering = ["-last_activity_at"]

    def __str__(self):
        return f"{self.user.email} - {self.key[:12]}..."

    @classmethod
    def generate_key(cls):
        raw = f"{uuid.uuid4()}{timezone.now().isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def create_session(cls, user, ip_address="", user_agent="", device="", lifetime_hours=72):
        cls.objects.filter(user=user, is_active=False).delete()
        cls.objects.filter(expires_at__lt=timezone.now()).delete()
        return cls.objects.create(
            key=cls.generate_key(),
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            device=device,
            expires_at=timezone.now() + timedelta(hours=lifetime_hours),
        )

    @classmethod
    def get_valid_session(cls, key):
        try:
            session = cls.objects.select_related("user").get(
                key=key, is_active=True, expires_at__gt=timezone.now()
            )
            session.save(update_fields=["last_activity_at"])
            return session
        except cls.DoesNotExist:
            return None

    def invalidate(self):
        self.is_active = False
        self.save(update_fields=["is_active"])

    @classmethod
    def invalidate_all(cls, user):
        cls.objects.filter(user=user, is_active=True).update(is_active=False)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at


class PasswordReset(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_resets")
    token = models.CharField(max_length=64, unique=True, db_index=True)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "password_resets"
        ordering = ["-created_at"]

    @classmethod
    def create_token(cls, user, lifetime_hours=1):
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        raw = f"{uuid.uuid4()}{user.pk}{timezone.now().isoformat()}"
        token = hashlib.sha256(raw.encode()).hexdigest()
        return cls.objects.create(
            user=user,
            token=token,
            expires_at=timezone.now() + timedelta(hours=lifetime_hours),
        )

    @classmethod
    def validate_token(cls, token):
        try:
            return cls.objects.select_related("user").get(
                token=token, is_used=False, expires_at__gt=timezone.now()
            )
        except cls.DoesNotExist:
            return None

    def consume(self):
        self.is_used = True
        self.save(update_fields=["is_used"])


class State(models.Model):
    abbreviation = models.CharField(max_length=2, primary_key=True)
    name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "states"
        ordering = ["abbreviation"]

    def __str__(self):
        return f"{self.abbreviation} - {self.name}"


class Route(models.Model):
    route_id = models.CharField(max_length=5, unique=True, db_index=True)
    origin_state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="origin_routes")
    destination_state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="destination_routes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "routes"
        ordering = ["route_id"]
        unique_together = ["origin_state", "destination_state"]

    def __str__(self):
        return self.route_id

    @classmethod
    def get_or_create_route(cls, origin_abbr, destination_abbr):
        route_id = f"{origin_abbr.upper()}-{destination_abbr.upper()}"
        route, _ = cls.objects.get_or_create(
            origin_state_id=origin_abbr.upper(),
            destination_state_id=destination_abbr.upper(),
            defaults={"route_id": route_id},
        )
        return route


class Facility(models.Model):
    class Type(models.TextChoices):
        WAREHOUSE = "warehouse"
        FULFILLMENT_CENTER = "fulfillment_center"
        SORTATION_CENTER = "sortation_center"
        DELIVERY_STATION = "delivery_station"
        CROSS_DOCK = "cross_dock"
        OTHER = "other"

    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    facility_type = models.CharField(max_length=30, choices=Type.choices, default=Type.WAREHOUSE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "facilities"
        verbose_name_plural = "facilities"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.city}, {self.state}"


class Load(models.Model):
    class DriverType(models.TextChoices):
        SOLO = "solo"
        TEAM = "team"

    class LoadType(models.TextChoices):
        DROP = "drop"
        LIVE = "live"
        HOOK = "hook"

    class Direction(models.TextChoices):
        ONE_WAY = "one_way"
        ROUND_TRIP = "round_trip"

    class Status(models.TextChoices):
        AVAILABLE = "available"
        BOOKED = "booked"
        IN_TRANSIT = "in_transit"
        DELIVERED = "delivered"
        CANCELLED = "cancelled"

    load_id = models.CharField(max_length=100, blank=True, db_index=True)
    tour_id = models.CharField(max_length=100, blank=True, db_index=True)
    route = models.ForeignKey(
        "Route", on_delete=models.SET_NULL, null=True, blank=True, related_name="loads"
    )

    origin_facility = models.CharField(max_length=100, db_index=True)
    origin_address = models.TextField(blank=True)
    origin_city = models.CharField(max_length=100, blank=True)
    origin_state = models.CharField(max_length=50, blank=True)
    origin_zip = models.CharField(max_length=20, blank=True)
    origin_datetime = models.DateTimeField(db_index=True)
    origin_timezone = models.CharField(max_length=10, blank=True)

    destination_facility = models.CharField(max_length=100, db_index=True)
    destination_address = models.TextField(blank=True)
    destination_city = models.CharField(max_length=100, blank=True)
    destination_state = models.CharField(max_length=50, blank=True)
    destination_zip = models.CharField(max_length=20, blank=True)
    destination_datetime = models.DateTimeField()
    destination_timezone = models.CharField(max_length=10, blank=True)

    total_stops = models.PositiveIntegerField(default=2)
    total_miles = models.DecimalField(max_digits=8, decimal_places=1)
    deadhead_miles = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    payout = models.DecimalField(max_digits=10, decimal_places=2)
    rate_per_mile = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    base_rate_per_mile = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    toll = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    driver_type = models.CharField(max_length=10, choices=DriverType.choices, default=DriverType.SOLO)
    load_type = models.CharField(max_length=10, choices=LoadType.choices, default=LoadType.DROP)
    equipment_type = models.CharField(max_length=50, default="53' Trailer")
    equipment_provided = models.BooleanField(default=True)

    direction = models.CharField(max_length=15, choices=Direction.choices, default=Direction.ONE_WAY)
    duration = models.CharField(max_length=20, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    special_services = models.TextField(blank=True)

    registered_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="registered_loads")
    assigned_driver = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_loads"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "loads"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["origin_facility", "destination_facility"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["origin_datetime"]),
            models.Index(fields=["-payout"]),
            models.Index(fields=["route", "created_at"]),
        ]

    def __str__(self):
        return f"{self.origin_facility} → {self.destination_facility} | ${self.payout}"

    @property
    def profit_per_mile(self):
        if self.total_miles:
            return round(self.payout / self.total_miles, 2)
        return 0


class LoadLeg(models.Model):
    class Status(models.TextChoices):
        EMPTY = "empty"
        LOADED = "loaded"

    load = models.ForeignKey(Load, on_delete=models.CASCADE, related_name="legs")
    leg_number = models.PositiveIntegerField()
    leg_code = models.CharField(max_length=50, blank=True)

    origin_facility = models.CharField(max_length=100)
    destination_facility = models.CharField(max_length=100)

    miles = models.DecimalField(max_digits=8, decimal_places=1)
    duration = models.CharField(max_length=20, blank=True)
    payout = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    load_type = models.CharField(max_length=10, choices=Load.LoadType.choices, default=Load.LoadType.DROP)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.LOADED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "load_legs"
        ordering = ["load", "leg_number"]
        unique_together = ["load", "leg_number"]

    def __str__(self):
        return f"Leg {self.leg_number}: {self.origin_facility} → {self.destination_facility}"


class Stop(models.Model):
    load = models.ForeignKey(Load, on_delete=models.CASCADE, related_name="stops")
    leg = models.ForeignKey(LoadLeg, on_delete=models.SET_NULL, null=True, blank=True, related_name="stops")
    stop_number = models.PositiveIntegerField()

    facility_code = models.CharField(max_length=100, db_index=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)

    equipment = models.CharField(max_length=50, blank=True)
    arrival_at = models.DateTimeField(null=True, blank=True)
    arrival_timezone = models.CharField(max_length=10, blank=True)
    departure_at = models.DateTimeField(null=True, blank=True)
    departure_timezone = models.CharField(max_length=10, blank=True)

    miles_to_next = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stops"
        ordering = ["load", "stop_number"]
        unique_together = ["load", "stop_number"]

    def __str__(self):
        return f"Stop {self.stop_number}: {self.facility_code}"


class ActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activity_logs")
    load = models.ForeignKey(Load, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_logs")
    action = models.CharField(max_length=50, db_index=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "activity_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.action}"