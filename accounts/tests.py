import io
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from PIL import Image
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
            reverse("profile"),
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


# test review
class ReviewEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="review_owner")
        cls.visitor = User.objects.create_user(username="review_visitor")

    def setUp(self):
        self.url = reverse("add_review", kwargs={"username": self.owner.username})

    def test_review_endpoint_requires_login(self):
        for method in (self.client.get, self.client.post):
            with self.subTest(method=method.__name__):
                response = method(self.url)
                self.assertRedirects(
                    response, f"{reverse('login')}?next={self.url}",
                    fetch_redirect_response=False,
                )
        self.assertFalse(self.owner.reviews_received.exists())

    def test_review_get_is_not_allowed(self):
        self.client.force_login(self.visitor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertFalse(self.owner.reviews_received.exists())

    def test_review_post_for_unknown_user_returns_404(self):
        self.client.force_login(self.visitor)
        response = self.client.post(
            reverse("add_review", kwargs={"username": "missing_review_user"})
        )
        self.assertEqual(response.status_code, 404)

    def test_self_review_post_redirects_to_own_profile(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url, {"rating": "5"})
        self.assertRedirects(response, reverse("profile"))
        self.assertFalse(self.owner.reviews_received.exists())

    def test_review_post_requires_completed_swap(self):
        for actor in (self.owner, self.visitor):
            with self.subTest(actor=actor.username):
                self.client.logout()
                self.client.force_login(actor)
                response = self.client.post(self.url, {
                    "rating": "5", "komentar": "Tidak boleh tersimpan.",
                    "pemberi_review": self.owner.pk,
                    "penerima_review": self.visitor.pk,
                })
                self.assertEqual(response.status_code, 302)
                expected_url = (
                    reverse("profile") if actor == self.owner
                    else reverse("public_profile", kwargs={"username": self.owner.username})
                )
                self.assertRedirects(response, expected_url)
        self.assertFalse(self.owner.reviews_received.exists())
        self.assertFalse(self.visitor.reviews_received.exists())

    def test_review_post_without_csrf_is_rejected(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.visitor)
        response = client.post(self.url, {"rating": "5"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.owner.reviews_received.exists())


class AccountUserAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="account_admin", email="admin@example.com",
            password="AdminAccount123!",
        )
        cls.member = User.objects.create_user(
            username="admin_member", password="OriginalMember123!",
            email="member@example.com",
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_admin_add_user_hashes_password(self):
        response = self.client.post(reverse("admin:accounts_user_add"), {
            "username": "new_admin_member", "usable_password": "true",
            "password1": "NewMemberPassword456!",
            "password2": "NewMemberPassword456!", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        member = User.objects.get(username="new_admin_member")
        self.assertTrue(member.check_password("NewMemberPassword456!"))
        self.assertNotEqual(member.password, "NewMemberPassword456!")

    def test_admin_change_form_protects_password_and_keeps_profile_fields(self):
        from django.contrib.auth.forms import ReadOnlyPasswordHashField

        response = self.client.get(reverse(
            "admin:accounts_user_change", args=[self.member.pk],
        ))
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertIsInstance(form.fields["password"], ReadOnlyPasswordHashField)
        for field in ("foto_profil", "bio", "lokasi"):
            with self.subTest(field=field):
                self.assertIn(field, form.fields)
        self.assertIn("is_verified", response.context["adminform"].readonly_fields)
        self.assertNotIn("is_verified", form.fields)

    def test_admin_password_change_preserves_login(self):
        response = self.client.post(reverse(
            "admin:auth_user_password_change", args=[self.member.pk],
        ), {
            "usable_password": "true",
            "password1": "ChangedMemberPassword789!",
            "password2": "ChangedMemberPassword789!",
        })
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password("ChangedMemberPassword789!"))
        self.assertTrue(self.client.login(
            username=self.member.username, password="ChangedMemberPassword789!",
        ))


class VerificationSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(
            username="verification_member", first_name="Nama", last_name="Awal",
            email="member@example.com", bio="Bio awal", lokasi="Depok",
        )
        cls.other = User.objects.create_user(
            username="verification_other", first_name="Akun", last_name="Lain",
            email="other@example.com",
        )
        cls.admin_user = User.objects.create_superuser(
            username="verification_admin", email="admin@example.com", password=None,
        )
        cls.staff = User.objects.create_user(username="limited_staff", is_staff=True)

    def approve(self):
        return Verification.objects.create(user=self.member, status="approved")

    def edit_data(self):
        return {
            "first_name": "Nama Diubah", "last_name": "Nama Baru",
            "email": "changed@example.com", "bio": "Bio baru",
            "lokasi": "Jakarta", "is_verified": "on",
        }

    def test_model_save_synchronizes_all_status_transitions(self):
        verification = Verification.objects.create(user=self.member)
        for status in ("approved", "pending", "approved", "rejected"):
            with self.subTest(status=status):
                verification.status = status
                verification.save(update_fields=["status"])
                self.member.refresh_from_db()
                self.assertEqual(self.member.is_verified, status == "approved")

    def test_unsaved_status_does_not_change_badge(self):
        verification = Verification.objects.create(user=self.member)
        verification.status = "approved"
        verification.save(update_fields=["tanggal_pengajuan"])
        verification.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual(verification.status, "pending")
        self.assertFalse(self.member.is_verified)

    def test_instance_delete_revokes_badge(self):
        verification = self.approve()
        verification.delete()
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_verified)

    def test_queryset_delete_revokes_badge(self):
        self.approve()
        Verification.objects.filter(user=self.member).delete()
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_verified)

    def test_invalid_status_is_not_saved(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            Verification.objects.create(user=self.member, status="invalid")
        self.assertFalse(Verification.objects.filter(user=self.member).exists())
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_verified)

    def test_model_cannot_approve_incomplete_or_invalid_identity(self):
        from django.core.exceptions import ValidationError

        for field, value in (("first_name", "   "), ("last_name", ""), ("email", "bukanemail")):
            with self.subTest(field=field):
                original = getattr(self.member, field)
                setattr(self.member, field, value)
                self.member.save(update_fields=[field])
                with self.assertRaises(ValidationError):
                    Verification.objects.create(user=self.member, status="approved")
                self.assertFalse(Verification.objects.filter(user=self.member).exists())
                self.member.refresh_from_db()
                self.assertFalse(self.member.is_verified)
                setattr(self.member, field, original)
                self.member.save(update_fields=[field])

    def test_verification_owner_cannot_be_reassigned(self):
        from django.core.exceptions import ValidationError

        verification = self.approve()
        verification.user = self.other
        with self.assertRaises(ValidationError):
            verification.save()
        verification.refresh_from_db()
        self.member.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(verification.user_id, self.member.pk)
        self.assertTrue(self.member.is_verified)
        self.assertFalse(self.other.is_verified)

    def test_request_rejects_invalid_email(self):
        self.member.email = "bukanemail"
        self.member.save(update_fields=["email"])
        self.client.force_login(self.member)
        response = self.client.post(reverse("request_verification"))
        self.assertRedirects(response, reverse("edit_profile"))
        self.assertFalse(Verification.objects.filter(user=self.member).exists())

    def test_request_rejects_whitespace_names(self):
        self.member.first_name = "   "
        self.member.save(update_fields=["first_name"])
        self.client.force_login(self.member)
        response = self.client.post(reverse("request_verification"))
        self.assertRedirects(response, reverse("edit_profile"))
        self.assertFalse(Verification.objects.filter(user=self.member).exists())

    def test_request_ignores_forged_user_and_status(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("request_verification"), {
            "user": self.other.pk, "status": "approved", "is_verified": "on",
        })
        self.assertRedirects(response, reverse("profile"))
        self.assertEqual(Verification.objects.get(user=self.member).status, "pending")
        self.assertFalse(Verification.objects.filter(user=self.other).exists())
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_verified)

    def test_request_requires_csrf(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.member)
        response = client.post(reverse("request_verification"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Verification.objects.filter(user=self.member).exists())

    def test_verified_profile_post_keeps_identity_and_updates_bio_location(self):
        self.approve()
        self.client.force_login(self.member)
        response = self.client.post(reverse("edit_profile"), self.edit_data())
        self.assertRedirects(response, reverse("profile"))
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Nama")
        self.assertEqual(self.member.last_name, "Awal")
        self.assertEqual(self.member.email, "member@example.com")
        self.assertEqual(self.member.bio, "Bio baru")
        self.assertEqual(self.member.lokasi, "Jakarta")
        self.assertTrue(self.member.is_verified)
        self.assertEqual(Verification.objects.get(user=self.member).status, "approved")

    def test_verified_form_locks_only_identity(self):
        from .forms import EditProfileForm

        self.approve()
        self.member.refresh_from_db()
        form = EditProfileForm(instance=self.member)
        for name in ("first_name", "last_name", "email"):
            with self.subTest(field=name):
                self.assertTrue(form.fields[name].disabled)
        for name in ("bio", "lokasi", "foto_profil"):
            with self.subTest(field=name):
                self.assertFalse(form.fields[name].disabled)

    def test_rejection_removes_badge_and_unlocks_identity(self):
        verification = self.approve()
        verification.status = "rejected"
        verification.save(update_fields=["status"])
        public_url = reverse("public_profile", kwargs={"username": self.member.username})
        self.assertNotContains(self.client.get(public_url), 'class="profile-verified"')
        self.client.force_login(self.member)
        response = self.client.post(reverse("edit_profile"), self.edit_data())
        self.assertRedirects(response, reverse("profile"))
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Nama Diubah")
        self.assertEqual(self.member.email, "changed@example.com")
        self.assertFalse(self.member.is_verified)

    def test_admin_cannot_approve_invalid_identity(self):
        verification = Verification.objects.create(user=self.member)
        self.member.email = "bukanemail"
        self.member.save(update_fields=["email"])
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse(
            "admin:accounts_verification_change", args=[verification.pk],
        ), {"status": "approved", "_save": "Save"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.non_field_errors())
        verification.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual(verification.status, "pending")
        self.assertFalse(self.member.is_verified)

    def test_admin_verified_identity_and_badge_are_readonly(self):
        self.approve()
        self.client.force_login(self.admin_user)
        url = reverse("admin:accounts_user_change", args=[self.member.pk])
        response = self.client.get(url)
        readonly = response.context["adminform"].readonly_fields
        for field in ("first_name", "last_name", "email", "is_verified"):
            with self.subTest(field=field):
                self.assertIn(field, readonly)
        data = self.edit_data()
        data.update({"username": self.member.username, "is_active": "on", "date_joined_0": "2026-10-27", "date_joined_1": "12:00:00"})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Nama")
        self.assertEqual(self.member.last_name, "Awal")
        self.assertEqual(self.member.email, "member@example.com")
        self.assertTrue(self.member.is_verified)
        self.assertEqual(self.member.bio, "Bio baru")

    def test_user_admin_permission_cannot_grant_verification(self):
        from django.contrib.auth.models import Permission

        self.staff.user_permissions.add(Permission.objects.get(
            content_type__app_label="accounts", content_type__model="user",
            codename="change_user",
        ))
        self.client.force_login(self.staff)
        data = self.edit_data()
        data.update({"username": self.member.username, "is_active": "on", "date_joined_0": "2026-10-27", "date_joined_1": "12:00:00"})
        response = self.client.post(reverse(
            "admin:accounts_user_change", args=[self.member.pk],
        ), data)
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_verified)
        verification = Verification.objects.create(user=self.member)
        response = self.client.post(reverse(
            "admin:accounts_verification_change", args=[verification.pk],
        ), {"status": "approved", "_save": "Save"})
        self.assertEqual(response.status_code, 403)
        verification.refresh_from_db()
        self.assertEqual(verification.status, "pending")


class ReviewValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.giver = User.objects.create_user(username="rating_giver")
        cls.receiver = User.objects.create_user(username="rating_receiver")

    def review(self, **changes):
        from .models import Review

        data = {
            "pemberi_review": self.giver, "penerima_review": self.receiver,
            "rating": "5", "komentar": "Pengalaman baik.",
        }
        data.update(changes)
        return Review(**data)

    def test_model_accepts_ratings_one_to_five(self):
        for rating in range(1, 6):
            with self.subTest(rating=rating):
                self.review(rating=rating).full_clean()

    def test_model_rejects_out_of_range_ratings(self):
        from django.core.exceptions import ValidationError

        for rating in ("0", "-1", "5.1", "6", "9.9"):
            with self.subTest(rating=rating):
                with self.assertRaises(ValidationError) as error:
                    self.review(rating=rating).full_clean()
                self.assertIn("rating", error.exception.message_dict)

    def test_model_rejects_self_review(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self.review(penerima_review=self.giver).full_clean()

    def test_save_rejects_self_review(self):
        from django.core.exceptions import ValidationError
        from .models import Review

        with self.assertRaises(ValidationError):
            self.review(penerima_review=self.giver).save()
        self.assertFalse(Review.objects.exists())

    def test_save_rejects_invalid_rating(self):
        from django.core.exceptions import ValidationError
        from .models import Review

        with self.assertRaises(ValidationError):
            self.review(rating="6").save()
        self.assertFalse(Review.objects.exists())

    def test_invalid_edit_keeps_existing_review(self):
        from django.core.exceptions import ValidationError
        from decimal import Decimal

        review = self.review()
        review.save()
        review.rating = "0"
        with self.assertRaises(ValidationError):
            review.save(update_fields=["rating"])
        review.refresh_from_db()
        self.assertEqual(review.rating, Decimal("5"))

    def test_model_allows_optional_comment(self):
        for comment in (None, ""):
            with self.subTest(comment=comment):
                review = self.review(komentar=comment)
                review.save()
                review.refresh_from_db()
                self.assertEqual(review.komentar, comment)

    def test_form_returns_decimal_for_each_star_choice(self):
        from decimal import Decimal
        from .forms import ReviewForm

        for rating in range(1, 6):
            with self.subTest(rating=rating):
                form = ReviewForm(data={"rating": str(rating), "komentar": "Bagus"})
                self.assertTrue(form.is_valid(), form.errors)
                self.assertIsInstance(form.cleaned_data["rating"], Decimal)
                self.assertEqual(form.cleaned_data["rating"], Decimal(rating))

    def test_form_rejects_missing_fractional_and_invalid_ratings(self):
        from .forms import ReviewForm

        for rating in (None, "", "0", "6", "3.5", "abc", "NaN", "Infinity"):
            with self.subTest(rating=rating):
                data = {} if rating is None else {"rating": rating}
                form = ReviewForm(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn("rating", form.errors)

    def test_form_strips_comment_whitespace(self):
        from .forms import ReviewForm

        form = ReviewForm(data={"rating": "4", "komentar": "  Rapi dan bersih.  "})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["komentar"], "Rapi dan bersih.")

    def test_form_allows_optional_comment(self):
        from .forms import ReviewForm

        for data in ({"rating": "4"}, {"rating": "4", "komentar": "   "}):
            with self.subTest(data=data):
                form = ReviewForm(data=data)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertFalse(form.cleaned_data["komentar"])

    def test_form_ignores_forged_review_ownership(self):
        from .forms import ReviewForm

        form = ReviewForm(instance=self.review(), data={
            "rating": "4", "komentar": "Bagus",
            "pemberi_review": self.receiver.pk, "penerima_review": self.giver.pk,
        })
        self.assertEqual(set(form.fields), {"rating", "komentar"})
        self.assertTrue(form.is_valid(), form.errors)
        review = form.save(commit=False)
        self.assertEqual(review.pemberi_review_id, self.giver.pk)
        self.assertEqual(review.penerima_review_id, self.receiver.pk)

    def test_form_rejects_self_review_instance(self):
        from .forms import ReviewForm

        form = ReviewForm(
            instance=self.review(penerima_review=self.giver),
            data={"rating": "5", "komentar": "Review diri sendiri"},
        )
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())


class ReviewProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from datetime import timedelta
        from django.utils import timezone
        from .models import Review

        cls.owner = User.objects.create_user(username="community_owner")
        cls.giver = User.objects.create_user(username="community_giver")
        cls.other = User.objects.create_user(username="community_other")
        cls.old_review = Review.objects.create(
            pemberi_review=cls.giver, penerima_review=cls.owner,
            rating="3", komentar="Komentar lebih lama.",
        )
        cls.new_review = Review.objects.create(
            pemberi_review=cls.other, penerima_review=cls.owner,
            rating="5", komentar="Komentar paling baru.",
        )
        Review.objects.filter(pk=cls.old_review.pk).update(
            tanggal=timezone.now() - timedelta(days=1),
        )
        Review.objects.create(
            pemberi_review=cls.owner, penerima_review=cls.other,
            rating="1", komentar="Review untuk pengguna lain.",
        )

    def setUp(self):
        self.url = reverse("public_profile", kwargs={"username": self.owner.username})

    def test_community_reviews_are_public_with_author_rating_comment_and_date(self):
        from django.utils import timezone

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for text in ("Community Reviews", self.giver.username, self.other.username,
                     "Komentar lebih lama.", "Komentar paling baru.", "5.0 / 5",
                     timezone.localtime(self.new_review.tanggal).strftime("%d %B %Y")):
            with self.subTest(text=text):
                self.assertContains(response, text)
        self.assertNotContains(response, "Review untuk pengguna lain.")

    def test_average_and_count_include_only_received_reviews(self):
        self.assertEqual(self.owner.get_rata_rata_rating(), 4.0)
        response = self.client.get(self.url)
        self.assertContains(response, "4.0 / 5")
        self.assertContains(response, "(2 reviews)")

    def test_average_rounds_to_one_decimal(self):
        from decimal import Decimal
        from .models import Review

        Review.objects.create(
            pemberi_review=self.giver, penerima_review=self.owner, rating="3",
        )
        self.assertEqual(self.owner.get_rata_rata_rating(), Decimal("3.7"))

    def test_profile_without_reviews_has_zero_average_and_empty_state(self):
        self.assertEqual(self.giver.get_rata_rata_rating(), 0.0)
        response = self.client.get(reverse(
            "public_profile", kwargs={"username": self.giver.username},
        ))
        self.assertContains(response, "No reviews yet.")
        self.assertNotContains(response, "(0 reviews)")

    def test_review_list_orders_newest_first(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertLess(content.index("Komentar paling baru."), content.index("Komentar lebih lama."))
        self.assertEqual(
            [review.pk for review in response.context["reviews"]],
            [self.new_review.pk, self.old_review.pk],
        )

    def test_my_profile_also_displays_received_reviews(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("profile"))
        self.assertContains(response, "Komentar paling baru.")
        self.assertContains(response, "(2 reviews)")
        self.assertNotContains(response, "Review untuk pengguna lain.")

    def test_form_is_hidden_without_swap_authorization(self):
        for actor in (None, self.owner, self.giver):
            with self.subTest(actor=actor.username if actor else "anonymous"):
                self.client.logout()
                if actor:
                    self.client.force_login(actor)
                response = self.client.get(self.url, {"can_review": "true"})
                self.assertFalse(response.context["can_review"])
                self.assertNotContains(response, "Leave a Review")
                self.assertNotContains(response, 'class="inline-review-form"')
                self.assertContains(response, "Community Reviews")

    def test_comment_html_is_escaped(self):
        self.new_review.komentar = '<script>alert("review")</script>'
        self.new_review.save(update_fields=["komentar"])
        response = self.client.get(self.url)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("review")</script>')


class AccountPhotoUploadTests(TestCase):
    """Uploaded profile photos are accepted by both account forms."""

    def make_photo(self):
        image_data = io.BytesIO()
        Image.new("RGB", (1, 1), color="red").save(image_data, format="PNG")
        return SimpleUploadedFile(
            "profile.png", image_data.getvalue(), content_type="image/png"
        )

    def storage_settings(self, media_root):
        return override_settings(
            MEDIA_ROOT=media_root,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                },
            },
        )

    def test_register_accepts_profile_photo(self):
        with tempfile.TemporaryDirectory() as media_root:
            with self.storage_settings(media_root):
                response = self.client.post(
                    reverse("register"),
                    {
                        "username": "photo_user",
                        "email": "photo@example.com",
                        "password1": "River!Cobalt72#",
                        "password2": "River!Cobalt72#",
                        "foto_profil": self.make_photo(),
                    },
                )

                self.assertRedirects(
                    response, reverse("login"), fetch_redirect_response=False
                )
                user = User.objects.get(username="photo_user")
                self.assertTrue(user.foto_profil.name)
                self.assertTrue(user.foto_profil.storage.exists(user.foto_profil.name))

    def test_edit_profile_accepts_profile_photo(self):
        user = User.objects.create_user(
            username="photo_editor",
            email="editor@example.com",
            password="EditorPass123!",
        )
        self.client.force_login(user)

        with tempfile.TemporaryDirectory() as media_root:
            with self.storage_settings(media_root):
                response = self.client.post(
                    reverse("edit_profile"),
                    {
                        "first_name": "Photo",
                        "last_name": "Editor",
                        "email": "editor@example.com",
                        "bio": "Updated with a photo",
                        "lokasi": "Jakarta",
                        "foto_profil": self.make_photo(),
                    },
                )

                self.assertRedirects(response, reverse("profile"))
                user.refresh_from_db()
                self.assertTrue(user.foto_profil.name)
                self.assertTrue(user.foto_profil.storage.exists(user.foto_profil.name))
