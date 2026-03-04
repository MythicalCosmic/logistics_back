from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from base.decorators.decorators import require_role
from admins.services.role_service import AdminRoleService
from admins.requests.role_requests import (
    create_role_request,
    update_role_request,
    assign_permission_request,
    remove_permission_request,
    bulk_assign_permissions_request,
)


def _json(result_tuple):
    data, status = result_tuple
    return JsonResponse(data, status=status)


@csrf_exempt
@require_GET
@require_role("admin")
def list_roles(request):
    return _json(AdminRoleService.list_roles())


@csrf_exempt
@require_POST
@require_role("admin")
def create_role(request):
    data, error = create_role_request(request)
    if error:
        return _json(error)

    return _json(AdminRoleService.create_role(
        name=data["name"],
        slug=data["slug"],
        description=data.get("description", ""),
    ))


@csrf_exempt
@require_GET
@require_role("admin")
def get_role(request, role_id):
    return _json(AdminRoleService.get_role(role_id))


@csrf_exempt
@require_http_methods(["PUT"])
@require_role("admin")
def update_role(request, role_id):
    data, error = update_role_request(request)
    if error:
        return _json(error)

    return _json(AdminRoleService.update_role(role_id, **data))


@csrf_exempt
@require_http_methods(["DELETE"])
@require_role("admin")
def delete_role(request, role_id):
    return _json(AdminRoleService.delete_role(role_id))


@csrf_exempt
@require_POST
@require_role("admin")
def assign_permission(request, role_id):
    data, error = assign_permission_request(request)
    if error:
        return _json(error)

    return _json(AdminRoleService.assign_permission(
        role_id=role_id,
        permission_id=data["permission_id"],
    ))


@csrf_exempt
@require_http_methods(["DELETE"])
@require_role("admin")
def remove_permission(request, role_id):
    data, error = remove_permission_request(request)
    if error:
        return _json(error)

    return _json(AdminRoleService.remove_permission(
        role_id=role_id,
        permission_id=data["permission_id"],
    ))


@csrf_exempt
@require_POST
@require_role("admin")
def bulk_assign_permissions(request, role_id):
    data, error = bulk_assign_permissions_request(request)
    if error:
        return _json(error)

    return _json(AdminRoleService.bulk_assign_permissions(
        role_id=role_id,
        permission_ids=data["permission_ids"],
    ))


@csrf_exempt
@require_GET
@require_role("admin")
def list_permissions(request):
    return _json(AdminRoleService.list_permissions())


@csrf_exempt
@require_GET
@require_role("admin")
def role_stats(request):
    return _json(AdminRoleService.stats())
