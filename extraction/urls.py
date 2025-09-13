from django.urls import path
from .views import HealthView, ExtractView, SplitPDFView

urlpatterns = [
    path('', HealthView.as_view()),
    path('health/', HealthView.as_view()),
    path('extract/', ExtractView.as_view()),
    path('split-pdf/', SplitPDFView.as_view()),
]
