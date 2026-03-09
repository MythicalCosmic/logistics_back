from django.urls import path

from main.views import auth_views, load_views, facility_views, route_views

urlpatterns = [
    path("login", auth_views.login, name="auth_login"),
    path("logout", auth_views.logout, name="auth_logout"),
    path("logout/all", auth_views.logout_all, name="auth_logout_all"),
    path("me", auth_views.me, name="auth_me"),
    path("password/change", auth_views.change_password, name="auth_change_password"),
    path("password/reset", auth_views.password_reset_request, name="auth_password_reset"),
    path("password/reset/confirm", auth_views.password_reset_confirm, name="auth_password_reset_confirm"),
    path("sessions", auth_views.sessions, name="auth_sessions"),

    # Loads
    path("loads", load_views.list_loads, name="load_list"),
    path("loads/stats", load_views.load_stats, name="load_stats"),
    path("loads/create", load_views.create_load, name="load_create"),
    path("loads/my", load_views.my_loads, name="load_my"),
    path("loads/<int:load_id>", load_views.get_load, name="load_detail"),
    path("loads/<int:load_id>/update", load_views.update_load, name="load_update"),
    path("loads/<int:load_id>/cancel", load_views.cancel_load, name="load_cancel"),
    path("loads/<int:load_id>/assign", load_views.assign_driver, name="load_assign"),
    path("loads/<int:load_id>/status", load_views.update_status, name="load_status"),

    # States & Routes
    path("states", route_views.list_states, name="state_list"),
    path("routes", route_views.list_routes, name="route_list"),
    path("routes/<str:route_id>", route_views.get_route, name="route_detail"),
    path("routes/<str:route_id>/loads", route_views.route_loads, name="route_loads"),
    path("routes/<str:route_id>/analytics", route_views.route_analytics, name="route_analytics"),

    # Facilities (read-only)
    path("facilities", facility_views.list_facilities, name="facility_list"),
    path("facilities/<int:facility_id>", facility_views.get_facility, name="facility_detail"),
]
