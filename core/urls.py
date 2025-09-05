from django.urls import path, include
from django.http import HttpResponse

def health_check(request):
    return HttpResponse("OK", content_type="text/plain")

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('', include('extraction.urls')),
]
