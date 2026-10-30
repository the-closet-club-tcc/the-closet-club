import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from closet.models import Clothing
from feed.models import OutfitPost


User = get_user_model()


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class FeedTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user1 = User.objects.create_user(
            username="alice",
            password="testpassword123",
        )
        cls.user2 = User.objects.create_user(
            username="bob",
            password="testpassword123",
        )

        cls.post1 = OutfitPost.objects.create(
            author=cls.user1,
            image=SimpleUploadedFile(
                "outfit1.jpg",
                b"test image content",
                content_type="image/jpeg",
            ),
            caption="Casual summer outfit",
        )

        cls.post2 = OutfitPost.objects.create(
            author=cls.user2,
            image=SimpleUploadedFile(
                "outfit2.jpg",
                b"test image content",
                content_type="image/jpeg",
            ),
            caption="Vintage denim outfit",
        )

    def test_feed_page_loads(self):
        response = self.client.get(reverse("feed:index"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "feed/feed_list.html")
        self.assertContains(response, "Casual summer outfit")
        self.assertContains(response, "Vintage denim outfit")

    def test_feed_is_public(self):
        response = self.client.get(reverse("feed:index"))

        self.assertEqual(response.status_code, 200)

    def test_post_detail_loads(self):
        response = self.client.get(
            reverse("feed:detail", args=[self.post1.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Casual summer outfit")

    def test_search_by_caption(self):
        response = self.client.get(
            reverse("feed:index"),
            {"q": "summer"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Casual summer outfit")
        self.assertNotContains(response, "Vintage denim outfit")

    def test_search_by_username(self):
        response = self.client.get(
            reverse("feed:index"),
            {"q": "alice"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Casual summer outfit")
        self.assertNotContains(response, "Vintage denim outfit")

    def test_search_is_case_insensitive(self):
        response = self.client.get(
            reverse("feed:index"),
            {"q": "SUMMER"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Casual summer outfit")

    def test_invalid_sort_defaults_to_newest(self):
        response = self.client.get(
            reverse("feed:index"),
            {"sort": "invalid"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sort"], "new")

    def test_popular_sort(self):
        self.post1.likes.add(self.user2)

        response = self.client.get(
            reverse("feed:index"),
            {"sort": "popular"},
        )

        self.assertEqual(response.status_code, 200)

        posts = list(response.context["page_obj"].object_list)

        self.assertEqual(posts[0].pk, self.post1.pk)

    def test_oldest_sort(self):
        response = self.client.get(
            reverse("feed:index"),
            {"sort": "oldest"},
        )

        self.assertEqual(response.status_code, 200)

        posts = list(response.context["page_obj"].object_list)

        self.assertEqual(posts[0].pk, self.post1.pk)

    def test_hero_shows_on_unfiltered_first_page(self):
        response = self.client.get(reverse("feed:index"))

        self.assertTrue(response.context["show_hero"])
        self.assertIn("hero_tiles", response.context)
        self.assertIn("hero_stats", response.context)

    def test_hero_hidden_when_searching(self):
        response = self.client.get(
            reverse("feed:index"),
            {"q": "summer"},
        )

        self.assertFalse(response.context["show_hero"])

    def test_hero_hidden_on_later_page(self):
        response = self.client.get(
            reverse("feed:index"),
            {"page": 2},
        )

        self.assertFalse(response.context["show_hero"])

    def test_guest_cannot_create_post(self):
        response = self.client.get(reverse("feed:create"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_guest_cannot_like_post(self):
        response = self.client.post(
            reverse("feed:like", args=[self.post1.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.post1.likes.exists())

    def test_authenticated_user_can_like_post(self):
        self.client.login(
            username="bob",
            password="testpassword123",
        )

        response = self.client.post(
            reverse("feed:like", args=[self.post1.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.post1.likes.filter(pk=self.user2.pk).exists())

    def test_user_can_unlike_post(self):
        self.post1.likes.add(self.user2)

        self.client.login(
            username="bob",
            password="testpassword123",
        )

        self.client.post(
            reverse("feed:like", args=[self.post1.pk])
        )

        self.assertFalse(self.post1.likes.filter(pk=self.user2.pk).exists())

    def test_like_requires_post_request(self):
        self.client.login(
            username="bob",
            password="testpassword123",
        )

        response = self.client.get(
            reverse("feed:like", args=[self.post1.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_user_can_delete_own_post(self):
        self.client.login(
            username="alice",
            password="testpassword123",
        )

        response = self.client.post(
            reverse("feed:delete", args=[self.post1.pk])
        )

        self.assertRedirects(response, reverse("feed:index"))
        self.assertFalse(
            OutfitPost.objects.filter(pk=self.post1.pk).exists()
        )

    def test_user_cannot_delete_another_users_post(self):
        self.client.login(
            username="bob",
            password="testpassword123",
        )

        response = self.client.post(
            reverse("feed:delete", args=[self.post1.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            OutfitPost.objects.filter(pk=self.post1.pk).exists()
        )

    def test_guest_cannot_delete_post(self):
        response = self.client.post(
            reverse("feed:delete", args=[self.post1.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            OutfitPost.objects.filter(pk=self.post1.pk).exists()
        )

    def test_delete_requires_post_request(self):
        self.client.login(
            username="alice",
            password="testpassword123",
        )

        response = self.client.get(
            reverse("feed:delete", args=[self.post1.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_nonexistent_post_returns_404(self):
        response = self.client.get(
            reverse("feed:detail", args=[999999])
        )

        self.assertEqual(response.status_code, 404)