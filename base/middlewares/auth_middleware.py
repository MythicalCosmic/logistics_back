from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from base.models import Session, User
from base.services.base_service import CacheService


PUBLIC_PATHS = [
    "/api/login",
    "/api/password/reset",
    "/api/password/reset/confirm",
    "/api/health",
    "/admin/",
]


class AuthMiddleware(MiddlewareMixin):

    def process_request(self, request):
        request.user = None
        request.session_obj = None

        if self._is_public(request.path):
            return None

        session_key = self._extract_session_key(request)
        if not session_key:
            return None

        cached_user_id = CacheService.get(f"session:{session_key}")
        if cached_user_id:
            try:
                request.user = User.objects.get(pk=cached_user_id)
                return None
            except User.DoesNotExist:
                CacheService.delete(f"session:{session_key}")

        session = Session.get_valid_session(session_key)
        if not session:
            return None

        request.user = session.user
        request.session_obj = session

        CacheService.set(f"session:{session_key}", session.user_id, ttl=300)

        return None

    def _extract_session_key(self, request) -> str:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Session "):
            return auth_header[8:].strip()
        return request.COOKIES.get("session_key", "")

    def _is_public(self, path: str) -> bool:
        return any(path.startswith(p) for p in PUBLIC_PATHS)


class PermissionMiddleware(MiddlewareMixin):

    PERMISSION_MAP = {
        "POST:/api/loads": "loads.create",
        "PUT:/api/loads": "loads.update",
        "DELETE:/api/loads": "loads.delete",
        "GET:/api/users": "users.view",
        "POST:/api/users": "users.create",
        "DELETE:/api/users": "users.delete",
    }

    def process_request(self, request):
        if not request.user:
            return None

        from base.models import User
        if not isinstance(request.user, User):
            return None

        method = request.method
        path_parts = request.path.rstrip("/").split("/")
        while path_parts and path_parts[-1].isdigit():
            path_parts.pop()
        normalized = "/".join(path_parts)

        lookup = f"{method}:{normalized}"
        required_permission = self.PERMISSION_MAP.get(lookup)

        if not required_permission:
            return None

        from base.services.role_permission_service import RolePermissionService
        permissions = RolePermissionService.get_cached_permissions(request.user.pk)

        if required_permission not in permissions:
            return JsonResponse(
                {"success": False, "message": "Insufficient permissions"}, status=403
            )

        return None
