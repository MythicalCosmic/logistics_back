from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from base.models import Session
from base.services.base_service import CacheService


# paths that dont need auth
PUBLIC_PATHS = [
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/password/reset",
    "/api/auth/password/reset/confirm",
    "/api/health",
]


class AuthMiddleware(MiddlewareMixin):

    def process_request(self, request):
        request.user = None
        request.session_obj = None

        #skip auth for public endpoints
        if self._is_public(request.path):
            return None

        #get session key from header or cookie
        session_key = self._extract_session_key(request)
        if not session_key:
            return JsonResponse(
                {"success": False, "message": "Authentication required"}, status=401
            )

        #try cache first for speed
        cached_session = CacheService.get(f"session:{session_key}")
        if cached_session:
            request.user = cached_session["user"]
            request.session_obj = cached_session
            return None

        #validate session from db
        session = Session.get_valid_session(session_key)
        if not session:
            return JsonResponse(
                {"success": False, "message": "Invalid or expired session"}, status=401
            )

        #attach to request
        request.user = session.user
        request.session_obj = session

        #cache for next request
        CacheService.set(f"session:{session_key}", {
            "user": session.user,
            "key": session.key,
            "user_id": session.user_id,
        }, ttl=300)

        return None

    def _extract_session_key(self, request) -> str:
        #check Authorization header first: "Session <key>"
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Session "):
            return auth_header[8:].strip()

        #fallback to cookie
        return request.COOKIES.get("session_key", "")

    def _is_public(self, path: str) -> bool:
        return any(path.startswith(p) for p in PUBLIC_PATHS)


class PermissionMiddleware(MiddlewareMixin):
    """check permissions based on endpoint mapping"""

    # endpoint -> required permission
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

        #build lookup key
        method = request.method
        #normalize path: /api/loads/123/ -> /api/loads
        path_parts = request.path.rstrip("/").split("/")
        #remove trailing numeric ids
        while path_parts and path_parts[-1].isdigit():
            path_parts.pop()
        normalized = "/".join(path_parts)

        lookup = f"{method}:{normalized}"
        required_permission = self.PERMISSION_MAP.get(lookup)

        if not required_permission:
            return None

        #check permission from cache
        from main.services.auth_service import AuthService
        permissions = AuthService.get_cached_permissions(request.user.pk)

        if required_permission not in permissions:
            return JsonResponse(
                {"success": False, "message": "Insufficient permissions"}, status=403
            )

        return None