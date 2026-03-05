import json

import pytest
from django.core.management import call_command
from django.test import Client, override_settings

from base.models import (
    User, Role, Permission, Session, Facility, Load, LoadLeg, Stop, ActivityLog,
)


# Override CACHES to LocMemCache so tests don't need Redis
TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}


def pytest_configure(config):
    """Apply test settings globally."""
    from django.conf import settings
    settings.CACHES = TEST_CACHES


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear LocMemCache before each test."""
    from django.core.cache import cache
    cache.clear()


@pytest.fixture
def api_client():
    return Client()


@pytest.fixture
def seed_permissions(db):
    """Seed all permissions and default roles."""
    call_command("seed_permissions", verbosity=0)


@pytest.fixture
def admin_role(seed_permissions):
    return Role.objects.get(slug="admin")


@pytest.fixture
def manager_role(seed_permissions):
    return Role.objects.get(slug="manager")


@pytest.fixture
def dispatcher_role(seed_permissions):
    return Role.objects.get(slug="dispatcher")


@pytest.fixture
def driver_role(seed_permissions):
    return Role.objects.get(slug="driver")


def _make_user(email, first_name="Test", last_name="User", password="TestPass1"):
    user = User(email=email, first_name=first_name, last_name=last_name)
    user.set_password(password)
    user.save()
    return user


@pytest.fixture
def admin_user(admin_role):
    user = _make_user("admin@test.com", "Admin", "User")
    user.assign_role("admin")
    return user


@pytest.fixture
def manager_user(manager_role):
    user = _make_user("manager@test.com", "Manager", "User")
    user.assign_role("manager")
    return user


@pytest.fixture
def dispatcher_user(dispatcher_role):
    user = _make_user("dispatcher@test.com", "Dispatcher", "User")
    user.assign_role("dispatcher")
    return user


@pytest.fixture
def driver_user(driver_role):
    user = _make_user("driver@test.com", "Driver", "User")
    user.assign_role("driver")
    return user


def make_session(user):
    """Create a valid session for a user and return the Session object."""
    return Session.create_session(user=user, ip_address="127.0.0.1", device="test")


@pytest.fixture
def admin_session(admin_user):
    return make_session(admin_user)


@pytest.fixture
def manager_session(manager_user):
    return make_session(manager_user)


@pytest.fixture
def dispatcher_session(dispatcher_user):
    return make_session(dispatcher_user)


@pytest.fixture
def driver_session(driver_user):
    return make_session(driver_user)


def auth_headers(session):
    """Return dict with HTTP_AUTHORIZATION header for a session."""
    return {"HTTP_AUTHORIZATION": f"Session {session.key}"}


@pytest.fixture
def admin_headers(admin_session):
    return auth_headers(admin_session)


@pytest.fixture
def manager_headers(manager_session):
    return auth_headers(manager_session)


@pytest.fixture
def dispatcher_headers(dispatcher_session):
    return auth_headers(dispatcher_session)


@pytest.fixture
def driver_headers(driver_session):
    return auth_headers(driver_session)


@pytest.fixture
def sample_facility(db):
    return Facility.objects.create(
        code="FAC001",
        name="Test Warehouse",
        address="123 Main St",
        city="Dallas",
        state="TX",
        zip_code="75001",
        facility_type="warehouse",
    )


def make_load(user, **overrides):
    """Create a load with sensible defaults."""
    from django.utils import timezone
    now = timezone.now()
    defaults = {
        "load_id": "LD-001",
        "tour_id": "TR-001",
        "origin_facility": "FAC001",
        "origin_city": "Dallas",
        "origin_state": "TX",
        "origin_datetime": now,
        "destination_facility": "FAC002",
        "destination_city": "Houston",
        "destination_state": "TX",
        "destination_datetime": now + timezone.timedelta(hours=5),
        "total_miles": 250.0,
        "payout": 500.00,
        "rate_per_mile": 2.00,
        "registered_by": user,
    }
    defaults.update(overrides)
    return Load.objects.create(**defaults)


@pytest.fixture
def sample_load(admin_user):
    return make_load(admin_user)


def post_json(client, url, data=None, **extra):
    """POST JSON to a URL via test client."""
    return client.post(
        url,
        data=json.dumps(data or {}),
        content_type="application/json",
        **extra,
    )


def put_json(client, url, data=None, **extra):
    """PUT JSON to a URL via test client."""
    return client.put(
        url,
        data=json.dumps(data or {}),
        content_type="application/json",
        **extra,
    )


def delete_json(client, url, data=None, **extra):
    """DELETE with JSON body to a URL via test client."""
    return client.delete(
        url,
        data=json.dumps(data or {}),
        content_type="application/json",
        **extra,
    )
