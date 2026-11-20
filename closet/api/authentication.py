from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Session cookie tanpa cek CSRF, karena klien mobile tidak punya token CSRF."""

    def enforce_csrf(self, request):
        return
