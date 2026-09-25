from django.urls import path

from . import views

urlpatterns = [
    path("", views.pipeline_list_view, name="agent-pipeline-list"),
    path("<int:pk>/", views.pipeline_detail_view, name="agent-pipeline-detail"),
]
