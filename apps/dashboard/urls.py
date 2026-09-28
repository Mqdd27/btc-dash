from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("health/", views.health_view, name="health"),
    path("health/db/", views.health_db_view, name="health-db"),
    path("health/redis/", views.health_redis_view, name="health-redis"),
    path("api/latest-signal/", views.latest_signal_view, name="latest-signal"),
    path("fragment/live-panel/", views.live_panel_fragment_view, name="live-panel-fragment"),
]
