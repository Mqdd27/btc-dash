from django.urls import path

from . import views

urlpatterns = [
    path("update/", views.update_engine_view, name="engine-update"),
]
