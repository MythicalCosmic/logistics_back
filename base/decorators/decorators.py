from functools import wraps

from django.http import JsonResponse

from base.services.role_permission_service import RolePermissionService


def _is_authenticated(request):
    user = getattr(request, "user", None)
    if user is None:
        return False
    from base.models import User
    return isinstance(user, User)


def require_auth(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not _is_authenticated(request):
            return JsonResponse(
                {"success": False, "message": "Authentication required"}, status=401
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def require_permission(*codenames):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not _is_authenticated(request):
                return JsonResponse(
                    {"success": False, "message": "Authentication required"}, status=401
                )

            permissions = RolePermissionService.get_cached_permissions(request.user.pk)
            if not any(c in permissions for c in codenames):
                return JsonResponse(
                    {"success": False, "message": "Insufficient permissions"}, status=403
                )

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_role(*slugs):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not _is_authenticated(request):
                return JsonResponse(
                    {"success": False, "message": "Authentication required"}, status=401
                )

            if not request.user.has_any_role(slugs):
                return JsonResponse(
                    {"success": False, "message": "Insufficient role"}, status=403
                )

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
