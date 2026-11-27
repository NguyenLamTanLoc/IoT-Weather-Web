from django.urls import path
from . import views

urlpatterns = [
    path("", views.overview, name="overview"),
    path("forecast/", views.forecast_page, name="forecast"),
    path("suggestions/", views.suggestions, name="suggestions"),
    path("history/", views.history, name="history"),
    path("settings/", views.settings_page, name="settings"),
    path("api/dashboard/", views.api_dashboard, name="api_dashboard"),
    path("api/export/", views.api_export, name="api_export"),
    path("api/ingest/", views.api_ingest, name="api_ingest"),
]
