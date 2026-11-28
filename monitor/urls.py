from django.urls import path
from . import views

urlpatterns = [
    path("", views.overview, name="overview"),
    path("forecast/", views.forecast_page, name="forecast"),
    path("suggestions/", views.suggestions, name="suggestions"),
    path("history/", views.history, name="history"),
    path("settings/", views.settings_page, name="settings"),
    path("forecast/csv/", views.csv_upload, name="csv_upload"),
    path("forecast/csv/check/", views.csv_check, name="csv_check"),
    path("forecast/csv/run/", views.csv_run, name="csv_run"),
    path("forecast/csv/result/", views.csv_result, name="csv_result"),
    path("settings/login/", views.admin_login, name="admin_login"),
    path("settings/logout/", views.admin_logout, name="admin_logout"),
    path("api/dashboard/", views.api_dashboard, name="api_dashboard"),
    path("api/export/", views.api_export, name="api_export"),
    path("api/ingest/", views.api_ingest, name="api_ingest"),
]
