import pytest
from django.test import RequestFactory

from base.middlewares.auth_middleware import AuthMiddleware
from base.models import User, Session


pytestmark = pytest.mark.django_db


def get_response(request):
    from django.http import JsonResponse
    return JsonResponse({"ok": True})


class TestAuthMiddleware:

    def _make_request(self, path="/api/test", auth_header=None, cookie=None):
        factory = RequestFactory()
        request = factory.get(path)
        if auth_header:
            request.META["HTTP_AUTHORIZATION"] = auth_header
        if cookie:
            request.COOKIES["session_key"] = cookie
        return request

    def test_public_path_skips_auth(self):
        mw = AuthMiddleware(get_response)
        request = self._make_request(path="/api/login")
        mw.process_request(request)
        assert request.user is None  # set to None but not rejected

    def test_valid_session_header(self, admin_user):
        session = Session.create_session(user=admin_user)
        mw = AuthMiddleware(get_response)
        request = self._make_request(auth_header=f"Session {session.key}")
        mw.process_request(request)
        assert request.user is not None
        assert request.user.pk == admin_user.pk

    def test_valid_session_cookie(self, admin_user):
        session = Session.create_session(user=admin_user)
        mw = AuthMiddleware(get_response)
        request = self._make_request(cookie=session.key)
        mw.process_request(request)
        assert request.user is not None
        assert request.user.pk == admin_user.pk

    def test_invalid_session_key(self):
        mw = AuthMiddleware(get_response)
        request = self._make_request(auth_header="Session invalidkey123")
        mw.process_request(request)
        assert request.user is None

    def test_missing_auth(self):
        mw = AuthMiddleware(get_response)
        request = self._make_request()
        mw.process_request(request)
        assert request.user is None

    def test_expired_session(self, admin_user):
        from datetime import timedelta
        from django.utils import timezone
        session = Session.create_session(user=admin_user)
        Session.objects.filter(key=session.key).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        mw = AuthMiddleware(get_response)
        request = self._make_request(auth_header=f"Session {session.key}")
        mw.process_request(request)
        assert request.user is None
