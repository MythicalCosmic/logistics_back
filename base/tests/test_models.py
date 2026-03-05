import pytest
from datetime import timedelta
from django.utils import timezone

from base.models import (
    User, Role, Permission, RolePermission, UserRole,
    Session, PasswordReset, Load, Facility,
)


pytestmark = pytest.mark.django_db


# ── User model ──────────────────────────────────────────────────────

class TestUserModel:

    def test_set_and_check_password(self):
        user = User(email="pw@test.com")
        user.set_password("Secret1234")
        user.save()
        assert user.check_password("Secret1234")
        assert not user.check_password("wrong")

    def test_full_name_with_names(self):
        user = User(email="x@x.com", first_name="John", last_name="Doe")
        assert user.full_name == "John Doe"

    def test_full_name_fallback_to_email(self):
        user = User(email="x@x.com")
        assert user.full_name == "x@x.com"

    def test_has_role(self, admin_user, seed_permissions):
        assert admin_user.has_role("admin")
        assert not admin_user.has_role("driver")

    def test_has_any_role(self, admin_user):
        assert admin_user.has_any_role(["admin", "driver"])
        assert not admin_user.has_any_role(["driver", "dispatcher"])

    def test_has_permission(self, admin_user):
        assert admin_user.has_permission("users.view")
        assert admin_user.has_permission("loads.create")

    def test_has_any_permission(self, admin_user):
        assert admin_user.has_any_permission(["users.view", "nonexistent"])
        assert not admin_user.has_any_permission(["nonexistent"])

    def test_get_permissions(self, admin_user):
        perms = list(admin_user.get_permissions())
        assert "users.view" in perms
        assert "loads.create" in perms

    def test_get_roles(self, admin_user):
        roles = list(admin_user.get_roles())
        assert "admin" in roles

    def test_assign_and_remove_role(self, seed_permissions):
        user = User(email="role@test.com")
        user.set_password("TestPass1")
        user.save()
        user.assign_role("driver")
        assert user.has_role("driver")
        user.remove_role("driver")
        assert not user.has_role("driver")

    def test_str(self):
        user = User(email="str@test.com")
        assert str(user) == "str@test.com"


# ── Role model ──────────────────────────────────────────────────────

class TestRoleModel:

    def test_has_permission(self, admin_role):
        assert admin_role.has_permission("users.view")

    def test_str(self, admin_role):
        assert str(admin_role) == "Admin"


# ── Session model ───────────────────────────────────────────────────

class TestSessionModel:

    def test_generate_key_is_64_hex(self):
        key = Session.generate_key()
        assert len(key) == 64
        int(key, 16)  # should not raise

    def test_create_session(self, admin_user):
        session = Session.create_session(user=admin_user, ip_address="1.2.3.4")
        assert session.key
        assert session.user == admin_user
        assert session.is_active
        assert not session.is_expired

    def test_get_valid_session(self, admin_user):
        session = Session.create_session(user=admin_user)
        found = Session.get_valid_session(session.key)
        assert found is not None
        assert found.key == session.key

    def test_get_valid_session_expired(self, admin_user):
        session = Session.create_session(user=admin_user, lifetime_hours=0)
        # Force expiry in the past
        Session.objects.filter(key=session.key).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        assert Session.get_valid_session(session.key) is None

    def test_get_valid_session_invalid_key(self):
        assert Session.get_valid_session("nonexistent") is None

    def test_invalidate(self, admin_user):
        session = Session.create_session(user=admin_user)
        session.invalidate()
        assert not session.is_active
        assert Session.get_valid_session(session.key) is None

    def test_invalidate_all(self, admin_user):
        Session.create_session(user=admin_user)
        Session.create_session(user=admin_user)
        assert Session.objects.filter(user=admin_user, is_active=True).count() == 2
        Session.invalidate_all(admin_user)
        assert Session.objects.filter(user=admin_user, is_active=True).count() == 0

    def test_is_expired_property(self, admin_user):
        session = Session.create_session(user=admin_user)
        assert not session.is_expired
        session.expires_at = timezone.now() - timedelta(hours=1)
        assert session.is_expired


# ── PasswordReset model ─────────────────────────────────────────────

class TestPasswordResetModel:

    def test_create_token(self, admin_user):
        reset = PasswordReset.create_token(admin_user)
        assert reset.token
        assert len(reset.token) == 64
        assert not reset.is_used

    def test_validate_token(self, admin_user):
        reset = PasswordReset.create_token(admin_user)
        found = PasswordReset.validate_token(reset.token)
        assert found is not None
        assert found.pk == reset.pk

    def test_validate_expired_token(self, admin_user):
        reset = PasswordReset.create_token(admin_user)
        PasswordReset.objects.filter(pk=reset.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        assert PasswordReset.validate_token(reset.token) is None

    def test_consume(self, admin_user):
        reset = PasswordReset.create_token(admin_user)
        reset.consume()
        assert reset.is_used
        assert PasswordReset.validate_token(reset.token) is None

    def test_create_token_invalidates_previous(self, admin_user):
        r1 = PasswordReset.create_token(admin_user)
        r2 = PasswordReset.create_token(admin_user)
        r1.refresh_from_db()
        assert r1.is_used
        assert not r2.is_used


# ── Load model ──────────────────────────────────────────────────────

class TestLoadModel:

    def test_profit_per_mile(self, sample_load):
        assert sample_load.profit_per_mile == round(500.00 / 250.0, 2)

    def test_profit_per_mile_zero_miles(self, admin_user):
        from conftest import make_load
        load = make_load(admin_user, total_miles=0, payout=100)
        assert load.profit_per_mile == 0

    def test_status_choices(self):
        choices = [c[0] for c in Load.Status.choices]
        assert "available" in choices
        assert "delivered" in choices
        assert "cancelled" in choices
