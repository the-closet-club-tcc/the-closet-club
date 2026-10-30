import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from closet.models import Clothes
from .models import OutfitPost

User = get_user_model()
TMP_MEDIA = tempfile.mkdtemp()

# 1x1 transparent GIF
GIF = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,'
       b'\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')


def make_image(name='outfit.gif'):
    return SimpleUploadedFile(name, GIF, content_type='image/gif')


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class FeedTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user('alice', password='pw12345!')
        self.bob = User.objects.create_user('bob', password='pw12345!')
        self.shirt = Clothes.objects.create(owner=self.alice, name='Denim shirt', size='M', condition='good')
        self.coat = Clothes.objects.create(owner=self.alice, name='Wool coat', size='L', condition='fair')
        self.post = OutfitPost.objects.create(author=self.alice, image=make_image(), caption='Autumn fit')
        self.post.clothes.add(self.shirt)

    def test_guest_can_browse_feed_and_detail(self):
        self.assertEqual(self.client.get(reverse('feed:index')).status_code, 200)
        self.assertEqual(self.client.get(self.post.get_absolute_url()).status_code, 200)

    def test_guest_cannot_create_or_like(self):
        r = self.client.get(reverse('feed:create'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('login', r.url)
        r = self.client.post(reverse('feed:like', args=[self.post.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.post.likes.count(), 0)

    def test_create_post_with_tagged_clothes(self):
        self.client.login(username='alice', password='pw12345!')
        r = self.client.post(reverse('feed:create'), {
            'image': make_image('new.gif'), 'caption': 'New look', 'clothes': [self.coat.pk],
        })
        self.assertEqual(r.status_code, 302)
        post = OutfitPost.objects.get(caption='New look')
        self.assertEqual(post.author, self.alice)
        self.assertEqual(list(post.clothes.all()), [self.coat])

    def test_cannot_tag_someone_elses_clothes(self):
        self.client.login(username='bob', password='pw12345!')
        r = self.client.post(reverse('feed:create'), {
            'image': make_image('x.gif'), 'caption': 'Sneaky', 'clothes': [self.shirt.pk],
        })
        self.assertEqual(r.status_code, 200)  # form re-rendered with errors
        self.assertFalse(OutfitPost.objects.filter(caption='Sneaky').exists())

    def test_like_toggle(self):
        self.client.login(username='bob', password='pw12345!')
        url = reverse('feed:like', args=[self.post.pk])
        self.client.post(url)
        self.assertEqual(self.post.likes.count(), 1)
        self.client.post(url)
        self.assertEqual(self.post.likes.count(), 0)

    def test_search_and_filters(self):
        other = OutfitPost.objects.create(author=self.bob, image=make_image('b.gif'), caption='Beach day')
        index = reverse('feed:index')
        self.assertContains(self.client.get(index, {'q': 'autumn'}), 'Autumn fit')
        self.assertNotContains(self.client.get(index, {'q': 'autumn'}), 'Beach day')
        # filter by size of tagged clothes
        res = self.client.get(index, {'size': 'M'})
        self.assertContains(res, 'Autumn fit')
        self.assertNotContains(res, 'Beach day')
        # invalid filter values are ignored, not crashing
        self.assertEqual(self.client.get(index, {'size': 'ZZZ', 'sort': 'hax'}).status_code, 200)
        self.assertTrue(other.pk)

    def test_only_author_can_delete(self):
        url = reverse('feed:delete', args=[self.post.pk])
        self.client.login(username='bob', password='pw12345!')
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(OutfitPost.objects.filter(pk=self.post.pk).exists())
        self.client.login(username='alice', password='pw12345!')
        self.client.post(url)
        self.assertFalse(OutfitPost.objects.filter(pk=self.post.pk).exists())

    def test_interested_button_links_to_chat(self):
        self.client.login(username='bob', password='pw12345!')
        res = self.client.get(self.post.get_absolute_url())
        self.assertContains(res, reverse('chat:start', args=[self.alice.pk]))
        self.assertContains(res, 'Interested')