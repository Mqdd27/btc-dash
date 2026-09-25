from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("backtests/", include("apps.backtest.urls")),
    path("walk-forward/", include("apps.ml.urls")),
    path("engine/", include("apps.trading.urls")),
    path("", include("apps.dashboard.urls")),
]
