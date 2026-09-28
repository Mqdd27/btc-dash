from django.urls import path

from . import views

urlpatterns = [
    path("update/", views.update_engine_view, name="engine-update"),
    path("evaluate-past/", views.evaluate_past_view, name="engine-evaluate-past"),
    path("paper/update/", views.update_paper_trading_view, name="paper-update"),
]
