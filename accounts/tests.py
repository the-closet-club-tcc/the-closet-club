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


# test profile dan edit profile

class ProfileTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="burhan",
            email="burhan@example.com",
            password="TestBurhan123",
            first_name="Burhan",
            last_name="Putra",
            bio="Suka thrifting",
            lokasi="Depok"
        )
        self.profile_url = reverse("profile")
        self.edit_url = reverse("edit_profile")

    # profile tidak bisa diakses tanpa login
    def test_profile_requires_login(self):
        response = self.client.get(self.profile_url)
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.profile_url}"
        )

    # profile menampilkan informasi user
    def test_profile_displays_user(self):
        self.client.force_login(self.user)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "accounts/profile.html"
        )

        self.assertContains(response, "Burhan Putra")
        self.assertContains(response, "Suka thrifting")
        self.assertContains(response, "Depok")

    # edit profile tidak bisa diakses tanpa login
    def test_edit_profile_requires_login(self):
        response = self.client.get(self.edit_url)
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.edit_url}"
        )

    # form edit profile menampilkan data lama
    def test_edit_profile_page(self):
        self.client.force_login(self.user)
        response = self.client.get(self.edit_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "accounts/edit_profile.html"
        )
        self.assertContains(response, "burhan@example.com")

    # perubahan profil berhasil disimpan
    def test_edit_profile_success(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.edit_url,
            {
                "first_name": "Burhania",
                "last_name": "Putri",
                "email": "burhania@example.com",
                "bio": "I love fashion",
                "lokasi": "Jakarta"
            }
        )

        self.assertRedirects(
            response,
            self.profile_url
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Burhania")
        self.assertEqual(self.user.last_name, "Putri")
        self.assertEqual(self.user.email, "burhania@example.com")
        self.assertEqual(self.user.bio, "I love fashion")
        self.assertEqual(self.user.lokasi, "Jakarta")

    # email tidak valid tidak boleh disimpan
    def test_edit_profile_invalid_email(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.edit_url,
            {
                "first_name": "Burhania",
                "last_name": "Putri",
                "email": "bukanemail",
                "bio": "Bio baru",
                "lokasi": "Jakarta"
            }
        )
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.email,
            "burhan@example.com"
        )

    # user tidak boleh memverifikasi diri sendiri
    def test_cannot_verify_self(self):
        self.client.force_login(self.user)
        self.client.post(
            self.edit_url,
            {
                "first_name": "Burhan",
                "last_name": "Putra",
                "email": "burhan@example.com",
                "bio": "Suka thrifting",
                "lokasi": "Depok",
                "is_verified": "on"
            }
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

# public profile test
class PublicProfileTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username = "sofita",
            email="sofita@example.com",
            password="TestSofita123"
        )
        self.visitor = User.objects.create_user(
            username = "burhan",
            password="TestBurhan123"
        )
        self.url = reverse(
            "public_profile", kwargs={"username": "sofita"}
        )

    # public profile bisa diliat tanpqa login
    def test_public_profile_without_login(self):
        response=self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "accounts/profile.html"
        )
        self.contains(response, "@sofita")

    # user lain tidak melihat tombol edit profile
    def test_visitor_cannot_edit_profile(self):
        self.client.force_login(self.visitor)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Edit Profile")

    # pemilik akun bisa melihat tombol edit profile
    def test_owner_can_see_edit_button(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, "Edit Profile")

    # profil tidak boleh mengekspos email pribadi
    def test_public_profile_hides_email(self):
        response = self.client.get(self.url)
        self.assertNotContains(
            response,
            "sofita@example.com"
        )

    # username yang tidak terdaftar menghasilkan 404
    def test_user_not_found(self):
        url = reverse(
            "public_profile",
            kwargs={"username": "tidakada"}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

