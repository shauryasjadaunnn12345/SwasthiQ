from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def health_view(request):
    return Response({"status": "ok", "service": "swasthiq-billing-api"})


urlpatterns = [
    path("", health_view),
]