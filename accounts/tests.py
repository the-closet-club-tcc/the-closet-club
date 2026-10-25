from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

# test register
class RegisterTests(TestCase):
    def setUp(self):
        self.url = reverse("register")
        self.data = {
            'username': 'burhania',
            'email': 'burhania@example.com',
            'password1':'TestBurhan123',
            'password2':'TestBurhan123'
        }
    def test_registter_page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "accounts/register.html"
        )

    def test_register_success(self):
        response = self.client.post(
            self.url,
            self.data
        )
        self.assertRedirects(
            response,
            reverse("login"),
            fetch_redirect_response=False
        )
        user = User.objects.get(username="burhania")

        self.assertEqual(
            user.email,
            "burhania@example.com"
        )
        self.assertTrue(
            user.check_password("TestBurhan123")
        )

    # test 3: password 2 berbeda
    def test_password_mismatch(self):
        data = self.data.copy()
        data["password2"] = "TestBurhanbeda123"

        response = self.client.post(
            self.url,
            data
        )

        self.assertEqual(response.status_code, 200)

        self.assertFalse(
            User.objects.filter(
                username="burhania"
            ).exists()
        )

    # test 4: username sudah digunakan
    def test_duplicate_username(self):
        User.objects.create_user(
            username="burhania",
            password="TestBurhan12345"
        )

        response = self.client.post(
            self.url,
            self.data
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            User.objects.filter(
                username="burhania"
            ).count(),
            1
        )

    # format email salah
    def test_invalid_email(self):
        data = self.data.copy()
        data["email"] = "bukanemail"

        response = self.client.post(
            self.url,
            data
        )

        self.assertEqual(response.status_code, 200)

        self.assertFalse(
            User.objects.filter(
                username="burhania"
            ).exists()
        )


# test login dan logout

class LoginTests(TestCase):

    def setUp(self):
        self.url = reverse("login")

        self.user = User.objects.create_user(
            username='burhania',
            email='burhania@example.com',
            password='TestBurhan123'
        )

    # test halaman login bisa dibuka
    def test_login_page(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        self.assertTemplateUsed(
            response,
            "accounts/login.html"
        )

    # test login berhasil membuat session
    def test_login_success(self):
        response = self.client.post(
            self.url,
            {
                "username": "burhania",
                "password": "TestBurhan123"
            }
        )

        self.assertRedirects(
            response,
            reverse("home"),
            fetch_redirect_response=False
        )

        self.assertEqual(
            self.client.session["_auth_user_id"],
            str(self.user.pk)
        )

    # test password login salah
    def test_login_wrong_password(self):
        response = self.client.post(
            self.url,
            {
                "username": "burhania",
                "password": "PassSalah123"
            }
        )

        self.assertEqual(response.status_code, 200)

        self.assertNotIn(
            "_auth_user_id",
            self.client.session
        )

    # test cookie last_login dibuat
    def test_last_login_cookie(self):
        response = self.client.post(
            self.url,
            {
                "username": "burhania",
                "password": "TestBurhan123"
            }
        )

        self.assertIn(
            "last_login",
            response.cookies
        )

    # test logout menghapus session
    def test_logout_success(self):
        self.client.post(
            self.url,
            {
                "username": "burhania",
                "password": "TestBurhan123"
            }
        )

        response = self.client.post(
            reverse("logout")
        )

        self.assertEqual(response.status_code, 302) #browser diarahkan keurl lain

        self.assertNotIn(
            "_auth_user_id",
            self.client.session
        )