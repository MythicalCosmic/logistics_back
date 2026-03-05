from django.urls import path

from admins.views import user_views, role_views, facility_views, activity_views

urlpatterns = [
    path("users", user_views.list_users, name="admin_list_users"),
    path("users/stats", user_views.user_stats, name="admin_user_stats"),
    path("users/create", user_views.create_user, name="admin_create_user"),
    path("users/<int:user_id>", user_views.get_user, name="admin_get_user"),
    path("users/<int:user_id>/update", user_views.update_user, name="admin_update_user"),
    path("users/<int:user_id>/delete", user_views.delete_user, name="admin_delete_user"),
    path("users/<int:user_id>/toggle-active", user_views.toggle_active, name="admin_toggle_active"),
    path("users/<int:user_id>/change-password", user_views.admin_change_password, name="admin_change_password"),
    path("users/<int:user_id>/force-logout", user_views.force_logout, name="admin_force_logout"),
    path("users/<int:user_id>/sessions", user_views.user_sessions, name="admin_user_sessions"),
    path("users/<int:user_id>/roles", user_views.assign_role, name="admin_assign_role"),
    path("users/<int:user_id>/roles/remove", user_views.remove_role, name="admin_remove_role"),

    path("roles", role_views.list_roles, name="admin_list_roles"),
    path("roles/stats", role_views.role_stats, name="admin_role_stats"),
    path("roles/create", role_views.create_role, name="admin_create_role"),
    path("roles/<int:role_id>", role_views.get_role, name="admin_get_role"),
    path("roles/<int:role_id>/update", role_views.update_role, name="admin_update_role"),
    path("roles/<int:role_id>/delete", role_views.delete_role, name="admin_delete_role"),
    path("roles/<int:role_id>/permissions", role_views.assign_permission, name="admin_assign_permission"),
    path("roles/<int:role_id>/permissions/remove", role_views.remove_permission, name="admin_remove_permission"),
    path("roles/<int:role_id>/permissions/bulk", role_views.bulk_assign_permissions, name="admin_bulk_assign_permissions"),

    path("permissions", role_views.list_permissions, name="admin_list_permissions"),

    # Facilities
    path("facilities", facility_views.list_facilities, name="admin_facility_list"),
    path("facilities/stats", facility_views.facility_stats, name="admin_facility_stats"),
    path("facilities/create", facility_views.create_facility, name="admin_facility_create"),
    path("facilities/<int:facility_id>", facility_views.get_facility, name="admin_facility_detail"),
    path("facilities/<int:facility_id>/update", facility_views.update_facility, name="admin_facility_update"),
    path("facilities/<int:facility_id>/delete", facility_views.delete_facility, name="admin_facility_delete"),

    # Activity Logs
    path("activity-logs", activity_views.list_logs, name="admin_activity_list"),
    path("activity-logs/<int:log_id>", activity_views.get_log, name="admin_activity_detail"),
]
