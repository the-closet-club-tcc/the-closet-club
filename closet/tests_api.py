import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import Clothing

User = get_user_model()
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix='tcc-api-media-')
TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


def make_photo(name='photo.png'):
    buf = BytesIO()
    Image.new('RGB', (10, 10), 'white').save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, STORAGES=TEST_STORAGES)
class ClosetListAPITests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user('alice', password='pass12345')
        self.bob = User.objects.create_user('bob', password='pass12345')
        self.url = reverse('closet:api_items')

    def make_item(self, owner, name, **kw):
        return Clothing.objects.create(owner=owner, name=name, photo=make_photo(), **kw)

    def test_requires_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)
        # Flutter memeriksa kata "credentials" pada pesan ini (lihat ChatService)
        self.assertIn('credentials', resp.json()['detail'].lower())

    def test_returns_only_my_items_newest_first(self):
        self.make_item(self.alice, 'First')
        self.make_item(self.alice, 'Second')
        self.make_item(self.bob, 'Bobs')
        self.client.login(username='alice', password='pass12345')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([i['name'] for i in resp.json()], ['Second', 'First'])

    def test_item_fields_and_absolute_photo_url(self):
        self.make_item(self.alice, 'Jacket', size='L', condition='very_good', status='barter')
        self.client.login(username='alice', password='pass12345')
        item = self.client.get(self.url).json()[0]
        for key in ['id', 'name', 'photo', 'size', 'size_display', 'condition',
                    'condition_display', 'description', 'status', 'status_display',
                    'owner', 'created_at']:
            self.assertIn(key, item)
        self.assertEqual(item['owner'], 'alice')
        self.assertEqual(item['status_display'], 'Open to swap')
        self.assertTrue(item['photo'].startswith('http'))

    def test_empty_list(self):
        self.client.login(username='alice', password='pass12345')
        self.assertEqual(self.client.get(self.url).json(), [])

    def test_post_not_allowed_yet(self):
        self.client.login(username='alice', password='pass12345')
        self.assertEqual(self.client.post(self.url, {}).status_code, 405)
