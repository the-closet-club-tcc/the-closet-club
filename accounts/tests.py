from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Verification

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
        self.assertContains(response, "@sofita")

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


# test verification
class VerificationTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="burhan",
            password="TestBurhan123",
            email="burhan@example.com",
            first_name="Burhan",
            last_name="Udin"
        )

        self.url = reverse("request_verification")

    # user harus login sebelum mengajukan verifikasi
    def test_verification_requires_login(self):
        response = self.client.post(self.url)

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.url}"
        )

        self.assertFalse(
            Verification.objects.filter(user=self.user).exists()
        )

    # pengajuan harus menggunakan POST, bukan GET
    def test_verification_requires_post(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertFalse(
            Verification.objects.filter(user=self.user).exists()
        )

    # tidak boleh mengajukan jika nama belum lengkap
    def test_verification_incomplete_name(self):
        self.user.first_name = ""
        self.user.save(update_fields=["first_name"])
        self.client.force_login(self.user)

        response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse("edit_profile")
        )

        self.assertFalse(
            Verification.objects.filter(user=self.user).exists()
        )

    # tidak boleh mengajukan jika email kosong
    def test_verification_missing_email(self):
        self.user.email = ""
        self.user.save(update_fields=["email"])

        self.client.force_login(self.user)

        response = self.client.post(self.url)

        self.assertRedirects(
            response,
            reverse("edit_profile")
        )

        self.assertFalse(
            Verification.objects.filter(user=self.user).exists()
        )

    # pengajuan baru berhasil dibuat dengan status pending
    def test_request_verification_success(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url)
        self.assertRedirects(
            response,
            reverse("profile")
        )

        verification = Verification.objects.get(user=self.user)

        self.assertEqual(verification.status, "pending")

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

    # klik pengajuan tidak membuat data duplikat
    def test_duplicate_verification_request(self):
        self.client.force_login(self.user)
        self.client.post(self.url)
        self.client.post(self.url)

        self.assertEqual(
            Verification.objects.filter(user=self.user).count(),
            1
        )

    # pengajuan yang ditolak boleh diajukan ulang
    def test_rejected_verification_can_retry(self):
        verification = Verification.objects.create(
            user=self.user,
            status="rejected"
        )

        self.client.force_login(self.user)
        response = self.client.post(self.url)
        verification.refresh_from_db()
        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(verification.status, "pending")
        self.assertEqual(
            Verification.objects.filter(user=self.user).count(),
            1
        )

    # user yang sudah verified tidak boleh mengajukan lagi
    def test_verified_user_cannot_request_again(self):
        self.user.is_verified = True
        self.user.save(update_fields=["is_verified"])

        verification = Verification.objects.create(
            user=self.user,
            status="approved"
        )
        self.client.force_login(self.user)
        response = self.client.post(self.url)
        verification.refresh_from_db()
        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(verification.status, "approved")

        self.assertEqual(
            Verification.objects.filter(user=self.user).count(),
            1
        )


# test admin

class VerificationAdminTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="burhan",
            password="TestBurhan123",
            first_name="Burhan",
            last_name="Udin",
            email="burhan@example.com"
        )

        self.admin_user = User.objects.create_superuser(
            username="admin_tcc",
            email="admin@example.com",
            password="AdminTest123"
        )

        # pengajuan awal berstatus pending
        self.verification = Verification.objects.create(
            user=self.user,
            status="pending"
        )

        self.admin_url = reverse(
            "admin:accounts_verification_change",
            args=[self.verification.pk]
        )

    # admin menyetujui verifikasi
    def test_admin_approve_verification(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            self.admin_url,
            {
                "status": "approved",
                "_save": "Save"
            }
        )

        self.assertEqual(response.status_code, 302)

        self.verification.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(
            self.verification.status,
            "approved"
        )

        self.assertTrue(self.user.is_verified)

        # badge verified harus muncul pada public profile
        profile_url = reverse(
            "public_profile",
            kwargs={"username": "burhan"}
        )

        response = self.client.get(profile_url)
        self.assertContains(
            response,
            'class="profile-verified"'
        )

    # admin menolak verifikasi
    def test_admin_reject_verification(self):
        # Anggap akun sebelumnya sudah verified
        self.verification.status = "approved"
        self.verification.save()

        self.user.is_verified = True
        self.user.save(update_fields=["is_verified"])

        self.client.force_login(self.admin_user)

        response = self.client.post(
            self.admin_url,
            {
                "status": "rejected",
                "_save": "Save"
            }
        )

        self.assertEqual(response.status_code, 302)

        self.verification.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(
            self.verification.status,
            "rejected"
        )

        self.assertFalse(self.user.is_verified)

    # user biasa tidak boleh approve melalui Django Admin
    def test_normal_user_cannot_approve(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.admin_url,
            {
                "status": "approved",
                "_save": "Save"
            }
        )

        # user biasa tidak mendapatkan akses admin
        self.assertEqual(response.status_code, 302)

        self.verification.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(
            self.verification.status,
            "pending"
        )

        self.assertFalse(self.user.is_verified)

