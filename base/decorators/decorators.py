from functools import wraps

from django.http import JsonResponse

from main.services.auth_service import AuthService


def require_auth(view_func):
    """ensure user is authenticated"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user:
            return JsonResponse(
                {"success": False, "message": "Authentication required"}, status=401
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def require_permission(*codenames):
    """check one or more permissions"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user:
                return JsonResponse(
                    {"success": False, "message": "Authentication required"}, status=401
                )

            permissions = AuthService.get_cached_permissions(request.user.pk)
            if not any(c in permissions for c in codenames):
                return JsonResponse(
                    {"success": False, "message": "Insufficient permissions"}, status=403
                )

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_role(*slugs):
    """check one or more roles"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user:
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