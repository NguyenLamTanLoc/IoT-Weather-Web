from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/dashboard/", views.api_dashboard, name="api_dashboard"),
    path("api/export/", views.api_export, name="api_export"),
    path("api/ingest/", views.api_ingest, name="api_ingest"),
]
