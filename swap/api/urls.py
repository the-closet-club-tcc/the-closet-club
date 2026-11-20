from django.urls import path

from swap.api.views import (
    IncomingSwapRequestAPIView,
    OutgoingSwapRequestAPIView,
)

urlpatterns = [
    path(
        'requests/incoming/',
        IncomingSwapRequestAPIView.as_view(),
        name='api_swap_requests_incoming',
    ),
    path(
        'requests/outgoing/',
        OutgoingSwapRequestAPIView.as_view(),
        name='api_swap_requests_outgoing',
    ),
]