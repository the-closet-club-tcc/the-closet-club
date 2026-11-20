
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from swap.models import SwapRequest
from swap.api.serializers import SwapRequestSerializer


class IncomingSwapRequestAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        swaps = SwapRequest.objects.filter(
            recipient=request.user
        )

        serializer = SwapRequestSerializer(swaps, many=True)
        return Response(serializer.data)


class OutgoingSwapRequestAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        swaps = SwapRequest.objects.filter(
            sender=request.user
        )

        serializer = SwapRequestSerializer(swaps, many=True)
        return Response(serializer.data)
