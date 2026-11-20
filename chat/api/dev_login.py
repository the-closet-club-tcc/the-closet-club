from django.conf import settings
from django.contrib.auth import authenticate, login
from django.http import Http404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class DevLoginAPI(APIView):
    """Temporary JSON login for local testing. Remove once accounts API exists."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.DEBUG:
            raise Http404
        user = authenticate(
            request._request,
            username=request.data.get('username', ''),
            password=request.data.get('password', ''),
        )
        if user is None:
            return Response(
                {'status': False, 'message': 'Invalid username or password.'}, status=401,
            )
        login(request._request, user)
        return Response(
            {'status': True, 'username': user.username, 'message': 'Login successful.'}
        )