import pytest
from django.http import JsonResponse

from base.services.base_service import ServiceResponse, Validator, CacheService


pytestmark = pytest.mark.django_db


class TestServiceResponse:

    def test_success(self):
        data, status = ServiceResponse.success("OK", data={"key": "val"})
        assert status == 200
        assert data["success"] is True
        assert data["data"]["key"] == "val"

    def test_success_no_data(self):
        data, status = ServiceResponse.success("Done")
        assert "data" not in data

    def test_success_custom_status(self):
        _, status = ServiceResponse.success("Created", status=201)
        assert status == 201

    def test_error(self):
        data, status = ServiceResponse.error("Bad input")
        assert status == 400
        assert data["success"] is False
        assert data["message"] == "Bad input"

    def test_unauthorized(self):
        data, status = ServiceResponse.unauthorized()
        assert status == 401

    def test_forbidden(self):
        data, status = ServiceResponse.forbidden()
        assert status == 403

    def test_not_found(self):
        data, status = ServiceResponse.not_found()
        assert status == 404

    def test_to_json(self):
        result = ServiceResponse.success("OK")
        response = ServiceResponse.to_json(result)
        assert isinstance(response, JsonResponse)
        assert response.status_code == 200


class TestValidator:

    def test_required_valid(self):
        v = Validator()
        v.required("hello", "field")
        assert v.is_valid

    def test_required_empty_string(self):
        v = Validator()
        v.required("", "field")
        assert not v.is_valid
        assert "field is required" in v.errors

    def test_required_none(self):
        v = Validator()
        v.required(None, "field")
        assert not v.is_valid

    def test_min_length(self):
        v = Validator()
        v.min_length("ab", 3, "field")
        assert not v.is_valid
        assert "at least 3" in v.errors

    def test_max_length(self):
        v = Validator()
        v.max_length("a" * 10, 5, "field")
        assert not v.is_valid
        assert "cannot exceed 5" in v.errors

    def test_email_valid(self):
        v = Validator()
        v.email("user@example.com")
        assert v.is_valid

    def test_email_invalid(self):
        v = Validator()
        v.email("notanemail")
        assert not v.is_valid

    def test_password_strength_valid(self):
        v = Validator()
        v.password_strength("StrongPass1")
        assert v.is_valid

    def test_password_strength_too_short(self):
        v = Validator()
        v.password_strength("Ab1")
        assert not v.is_valid

    def test_password_strength_no_uppercase(self):
        v = Validator()
        v.password_strength("alllowercase1")
        assert not v.is_valid

    def test_password_strength_no_digit(self):
        v = Validator()
        v.password_strength("NoDigitHere")
        assert not v.is_valid

    def test_chaining(self):
        v = Validator()
        v.required("x", "f").min_length("x", 5, "f")
        assert not v.is_valid

    def test_multiple_errors_semicolon_separated(self):
        v = Validator()
        v.required("", "a").required("", "b")
        assert ";" in v.errors


class TestCacheService:

    def test_set_and_get(self):
        CacheService.set("testkey", {"foo": "bar"})
        assert CacheService.get("testkey") == {"foo": "bar"}

    def test_get_missing(self):
        assert CacheService.get("nonexistent") is None

    def test_delete(self):
        CacheService.set("delme", "value")
        CacheService.delete("delme")
        assert CacheService.get("delme") is None

    def test_get_or_set(self):
        result = CacheService.get_or_set("computed", lambda: 42)
        assert result == 42
        assert CacheService.get("computed") == 42

    def test_get_or_set_uses_cached(self):
        CacheService.set("cached", 100)
        result = CacheService.get_or_set("cached", lambda: 200)
        assert result == 100

    def test_delete_pattern_no_crash(self):
        # delete_pattern uses Redis internals, with LocMemCache it should just pass
        CacheService.delete_pattern("test:*")
