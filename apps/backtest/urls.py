from django.urls import path

from . import views

urlpatterns = [
    path("", views.backtest_list_view, name="backtest-list"),
    path("create/", views.backtest_create_view, name="backtest-create"),
    path("compare/", views.backtest_compare_view, name="backtest-compare"),
    path("<int:pk>/", views.backtest_detail_view, name="backtest-detail"),
    path("<int:pk>/status/", views.backtest_status_partial_view, name="backtest-status"),
    path("<int:pk>/trades/", views.backtest_trades_partial_view, name="backtest-trades"),
]
