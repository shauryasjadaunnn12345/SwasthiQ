from django.urls import include, path

urlpatterns = [
    path("", include("billing.health_urls")),
    path("api/", include("billing.urls")),
]
