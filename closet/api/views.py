from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import CsrfExemptSessionAuthentication
from .serializers import ClothingSerializer


class ClosetAPIView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [IsAuthenticated]


class ClothingListAPI(ClosetAPIView):
    """Daftar pakaian milik user yang sedang login, terbaru dulu."""

    def get(self, request):
        items = request.user.clothes.all()
        data = ClothingSerializer(items, many=True, context={'request': request}).data
        return Response(data)
