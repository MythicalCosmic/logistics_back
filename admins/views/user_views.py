from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from base.decorators.decorators import require_permission
from base.helpers.auth_helpers import _parse_body
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
@require_permission("users.view")
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
@require_permission("users.create")
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
@require_permission("users.view")
def get_user(request, user_id):
    return _json(AdminUserService.get_user(user_id))


@csrf_exempt
@require_http_methods(["PUT"])
@require_permission("users.update")
def update_user(request, user_id):
    data, error = update_user_request(request)
    if error:
        return _json(error)

    return _json(AdminUserService.update_user(user_id, **data))


@csrf_exempt
@require_http_methods(["DELETE"])
@require_permission("users.delete")
def delete_user(request, user_id):
    body = _parse_body(request)
    force = body.get("force", False) is True

    return _json(AdminUserService.delete_user(
        user_id=user_id,
        admin_id=request.user.pk,
        force=force,
    ))


@csrf_exempt
@require_POST
@require_permission("users.update")
def toggle_active(request, user_id):
    body = _parse_body(request)
    force = body.get("force", False) is True

    return _json(AdminUserService.toggle_active(
        user_id=user_id,
        admin_id=request.user.pk,
        force=force,
    ))


@csrf_exempt
@require_POST
@require_permission("users.update")
def admin_change_password(request, user_id):
    data, error = change_password_request(request)
    if error:
        return _json(error)

    return _json(AdminUserService.change_password(
        user_id=user_id,
        new_password=data["new_password"],
        admin_id=request.user.pk,
        force=data.get("force", False),
    ))


@csrf_exempt
@require_POST
@require_permission("users.update")
def force_logout(request, user_id):
    body = _parse_body(request)
    force = body.get("force", False) is True

    return _json(AdminUserService.force_logout(
        user_id=user_id,
        admin_id=request.user.pk,
        force=force,
    ))


@csrf_exempt
@require_GET
@require_permission("users.view")
def user_sessions(request, user_id):
    return _json(AdminUserService.get_user_sessions(user_id))


@csrf_exempt
@require_POST
@require_permission("roles.update")
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
@require_permission("roles.update")
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
@require_permission("users.view")
def user_stats(request):
    return _json(AdminUserService.stats())
