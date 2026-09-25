from django.urls import path

from . import views

urlpatterns = [
    path("", views.walk_forward_list_view, name="walk-forward-list"),
    path("<int:pk>/", views.walk_forward_detail_view, name="walk-forward-detail"),
]
