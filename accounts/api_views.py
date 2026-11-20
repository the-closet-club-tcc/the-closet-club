from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Review, User, Verification
from .serializers import ReviewSerializer, UserSerializer, VerificationSerializer


class UserListAPIView(generics.ListAPIView):
    queryset = User.objects.all().order_by("username")
    serializer_class = UserSerializer
    permission_classes = [AllowAny]


class PublicProfileAPIView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    lookup_field = "username"
    permission_classes = [AllowAny]


class CurrentUserProfileAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserReviewsAPIView(generics.ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        user = get_object_or_404(User, username=self.kwargs["username"])
        return Review.objects.filter(penerima_review=user).order_by("-tanggal")


class VerificationStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        verification = Verification.objects.filter(user=request.user).first()
        if verification is None:
            return Response(
                {
                    "is_verified": request.user.is_verified,
                    "status": "not_submitted",
                }
            )
        serializer = VerificationSerializer(verification)
        return Response(serializer.data)