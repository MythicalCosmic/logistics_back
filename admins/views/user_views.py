from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from base.decorators.decorators import require_role
from admins.services.user_service import AdminUserService
from admins.requests.user_requests import (
    create_user_request,
    update_user_request,
    list_users_request,
    assign_role_request,
    remove_role_request,
    change_password_request,
)


def _json(result_tuple):
    data, status = result_tuple
    return JsonResponse(data, status=status)


@csrf_exempt
@require_GET
@require_role("admin")
def list_users(request):
    data, error = list_users_request(request)
    if error:
        return _json(error)

    return _json(AdminUserService.list_users(
        page=data["page"],
        per_page=data["per_page"],
        search=data["search"],
        is_active=data.get("is_active"),
        role_slug=data.get("role_slug", ""),
        sort_by=data.get("sort_by", "-created_at"),
    ))


@csrf_exempt
@require_POST
@require_role("admin")
def create_user(request):
    data, error = create_user_request(request)
    if error:
        return _json(error)

    return _json(AdminUserService.create_user(
        email=data["email"],
        first_name=data["first_name"],
        last_name=data["last_name"],
        password=data["password"],
        phone=data.get("phone", ""),
        role_id=data.get("role_id"),
    ))


@csrf_exempt
@require_GET
@require_role("admin")
def get_user(request, user_id):
    return _json(AdminUserService.get_user(user_id))


@csrf_exempt
@require_http_methods(["PUT"])
@require_role("admin")
def update_user(request, user_id):
    data, error = update_user_request(request)
    if error:
        return _json(error)

    return _json(AdminUserService.update_user(user_id, **data))


@csrf_exempt
@require_http_methods(["DELETE"])
@require_role("admin")
def delete_user(request, user_id):
    return _json(AdminUserService.delete_user(user_id))


@csrf_exempt
@require_POST
@require_role("admin")
def toggle_active(request, user_id):
    return _json(AdminUserService.toggle_active(user_id))


@csrf_exempt
@require_POST
@require_role("admin")
def admin_change_password(request, user_id):
    data, error = change_password_request(request)
    if error:
        return _json(error)

    return _json(AdminUserService.change_password(user_id, data["new_password"]))


@csrf_exempt
@require_POST
@require_role("admin")
def force_logout(request, user_id):
    return _json(AdminUserService.force_logout(user_id))


@csrf_exempt
@require_GET
@require_role("admin")
def user_sessions(request, user_id):
    return _json(AdminUserService.get_user_sessions(user_id))


@csrf_exempt
@require_POST
@require_role("admin")
def assign_role(request, user_id):
    data, error = assign_role_request(request)
    if error:
        return _json(error)

    return _json(AdminUserService.assign_role(
        user_id=user_id,
        role_id=data["role_id"],
        assigned_by=request.user,
    ))


@csrf_exempt
@require_http_methods(["DELETE"])
@require_role("admin")
def remove_role(request, user_id):
    data, error = remove_role_request(request)
    if error:
        return _json(error)

    return _json(AdminUserService.remove_role(
        user_id=user_id,
        role_id=data["role_id"],
    ))


@csrf_exempt
@require_GET
@require_role("admin")
def user_stats(request):
    return _json(AdminUserService.stats())
