import json

import pytest
from django.test import Client

from base.models import User, Session, PasswordReset
from conftest import post_json, auth_headers, make_session


pytestmark = pytest.mark.django_db


class TestLogin:

    def test_valid_login(self, api_client, admin_user):
        resp = post_json(api_client, "/api/login", {
            "email": "admin@test.com",
            "password": "TestPass1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "session_key" in data["data"]
        assert data["data"]["user"]["email"] == "admin@test.com"

    def test_wrong_password(self, api_client, admin_user):
        resp = post_json(api_client, "/api/login", {
            "email": "admin@test.com",
            "password": "WrongPass1",
        })
        assert resp.status_code == 401
        assert resp.json()["success"] is False

    def test_wrong_email(self, api_client, admin_user):
        resp = post_json(api_client, "/api/login", {
            "email": "nonexistent@test.com",
            "password": "TestPass1",
        })
        assert resp.status_code == 401

    def test_missing_fields(self, api_client):
        resp = post_json(api_client, "/api/login", {})
        assert resp.status_code == 400

    def test_password_too_short(self, api_client):
        resp = post_json(api_client, "/api/login", {
            "email": "x@x.com",
            "password": "short",
        })
        assert resp.status_code == 400

    def test_rate_limiting(self, api_client, admin_user):
        for _ in range(6):
            post_json(api_client, "/api/login", {
                "email": "admin@test.com",
                "password": "WrongPass1",
            })
        resp = post_json(api_client, "/api/login", {
            "email": "admin@test.com",
            "password": "WrongPass1",
        })
        assert resp.status_code == 429

    def test_inactive_user_cannot_login(self, api_client, admin_user):
        admin_user.is_active = False
        admin_user.save()
        resp = post_json(api_client, "/api/login", {
            "email": "admin@test.com",
            "password": "TestPass1",
        })
        assert resp.status_code == 401

    def test_login_sets_cookie(self, api_client, admin_user):
        resp = post_json(api_client, "/api/login", {
            "email": "admin@test.com",
            "password": "TestPass1",
        })
        assert "session_key" in resp.cookies

    def test_get_method_not_allowed(self, api_client):
        resp = api_client.get("/api/login")
        assert resp.status_code == 405


class TestLogout:

    def test_valid_logout(self, api_client, admin_session):
        headers = auth_headers(admin_session)
        resp = post_json(api_client, "/api/logout", {}, **headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_logout_invalid_session(self, api_client):
        resp = post_json(api_client, "/api/logout", {},
                         HTTP_AUTHORIZATION="Session invalidkey")
        assert resp.status_code == 401

    def test_logout_no_session(self, api_client):
        resp = post_json(api_client, "/api/logout", {})
        assert resp.status_code == 401


class TestLogoutAll:

    def test_valid_logout_all(self, api_client, admin_user, admin_session):
        # Create extra session
        make_session(admin_user)
        headers = auth_headers(admin_session)
        resp = post_json(api_client, "/api/logout/all", {}, **headers)
        assert resp.status_code == 200
        assert Session.objects.filter(user=admin_user, is_active=True).count() == 0


class TestMe:

    def test_authenticated(self, api_client, admin_session):
        headers = auth_headers(admin_session)
        resp = api_client.get("/api/me", **headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["email"] == "admin@test.com"

    def test_unauthenticated(self, api_client):
        resp = api_client.get("/api/me")
        assert resp.status_code == 401


class TestChangePassword:

    def test_valid_change(self, api_client, admin_session):
        headers = auth_headers(admin_session)
        resp = post_json(api_client, "/api/password/change", {
            "current_password": "TestPass1",
            "new_password": "NewPass123",
        }, **headers)
        assert resp.status_code == 200

    def test_wrong_current_password(self, api_client, admin_session):
        headers = auth_headers(admin_session)
        resp = post_json(api_client, "/api/password/change", {
            "current_password": "WrongPass1",
            "new_password": "NewPass123",
        }, **headers)
        assert resp.status_code == 400

    def test_weak_new_password(self, api_client, admin_session):
        headers = auth_headers(admin_session)
        resp = post_json(api_client, "/api/password/change", {
            "current_password": "TestPass1",
            "new_password": "weak",
        }, **headers)
        assert resp.status_code == 400

    def test_unauthenticated(self, api_client):
        resp = post_json(api_client, "/api/password/change", {
            "current_password": "TestPass1",
            "new_password": "NewPass123",
        })
        assert resp.status_code == 401


class TestPasswordReset:

    def test_request_reset(self, api_client, admin_user):
        resp = post_json(api_client, "/api/password/reset", {
            "email": "admin@test.com",
        })
        assert resp.status_code == 200
        # Always returns success even for non-existent emails
        assert resp.json()["success"] is True

    def test_request_reset_nonexistent_email(self, api_client, db):
        resp = post_json(api_client, "/api/password/reset", {
            "email": "nobody@test.com",
        })
        assert resp.status_code == 200  # prevents email enumeration

    def test_confirm_reset(self, api_client, admin_user):
        reset = PasswordReset.create_token(admin_user)
        resp = post_json(api_client, "/api/password/reset/confirm", {
            "token": reset.token,
            "new_password": "BrandNew1",
        })
        assert resp.status_code == 200
        admin_user.refresh_from_db()
        assert admin_user.check_password("BrandNew1")

    def test_confirm_invalid_token(self, api_client, db):
        resp = post_json(api_client, "/api/password/reset/confirm", {
            "token": "invalidtoken",
            "new_password": "BrandNew1",
        })
        assert resp.status_code == 400


class TestSessions:

    def test_list_sessions(self, api_client, admin_session):
        headers = auth_headers(admin_session)
        resp = api_client.get("/api/sessions", **headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_revoke_session(self, api_client, admin_user, admin_session):
        other = make_session(admin_user)
        headers = auth_headers(admin_session)
        resp = api_client.delete(
            "/api/sessions",
            data=json.dumps({"session_key": other.key}),
            content_type="application/json",
            **headers,
        )
        assert resp.status_code == 200

    def test_unauthenticated(self, api_client):
        resp = api_client.get("/api/sessions")
        assert resp.status_code == 401
