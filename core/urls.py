from django.urls import path, include
from django.http import HttpResponse
from django.conf import settings
from django.conf.urls.static import static

def health_check(request):
    return HttpResponse("OK", content_type="text/plain")

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('', include('extraction.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
