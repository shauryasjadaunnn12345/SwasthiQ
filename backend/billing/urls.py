from django.urls import path

from billing import views

urlpatterns = [
    path("clinics/<str:clinic_id>/days/", views.days_view),
    path("clinics/<str:clinic_id>/days/<str:date_str>/ingest/", views.ingest_view),
    path("clinics/<str:clinic_id>/days/<str:date_str>/reconciliation/", views.reconciliation_view),
    path("clinics/<str:clinic_id>/days/<str:date_str>/analytics/", views.analytics_view),
    path("clinics/<str:clinic_id>/days/<str:date_str>/narrative/", views.narrative_view),
]
