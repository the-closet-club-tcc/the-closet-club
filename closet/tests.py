import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .forms import ClothingForm
from .models import Clothing

User = get_user_model()
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix='tcc-test-media-')


def make_photo(name='photo.png', size=(20, 20)):
    buf = BytesIO()
    Image.new('RGB', size, 'white').save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ClosetTestBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user('alice', password='pass12345')
        self.bob = User.objects.create_user('bob', password='pass12345')

    def login(self, user):
        self.assertTrue(self.client.login(username=user.username, password='pass12345'))

    def make_item(self, owner=None, name='Denim Jacket', status=Clothing.Status.PERSONAL, **kw):
        return Clothing.objects.create(
            owner=owner or self.alice, name=name, photo=make_photo(),
            size=kw.pop('size', 'M'), condition=kw.pop('condition', 'good'),
            status=status, **kw,
        )


class ModelTests(ClosetTestBase):
    def test_is_offered_only_for_offer_statuses(self):
        for status, expected in [
            (Clothing.Status.PERSONAL, False), (Clothing.Status.BARTER, True),
            (Clothing.Status.TOP_UP, True), (Clothing.Status.DONATE, True),
            (Clothing.Status.SWAPPED, False),
        ]:
            self.assertEqual(self.make_item(status=status).is_offered, expected, status)

    def test_offered_queryset(self):
        self.make_item(name='a', status=Clothing.Status.PERSONAL)
        offered = self.make_item(name='b', status=Clothing.Status.BARTER)
        self.assertEqual(list(Clothing.objects.offered()), [offered])

    def test_photo_file_removed_on_delete(self):
        item = self.make_item()
        storage, name = item.photo.storage, item.photo.name
        self.assertTrue(storage.exists(name))
        item.delete()
        self.assertFalse(storage.exists(name))


class MyClosetViewTests(ClosetTestBase):
    def test_requires_login(self):
        for url in [
            reverse('closet:my_closet'), reverse('closet:item_add'),
            reverse('closet:item_edit', args=[1]), reverse('closet:item_delete', args=[1]),
        ]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, url)
            self.assertIn('/accounts/login/', resp['Location'])

    def test_lists_only_own_items(self):
        self.make_item(name='Mine')
        self.make_item(owner=self.bob, name='Theirs')
        self.login(self.alice)
        resp = self.client.get(reverse('closet:my_closet'))
        self.assertContains(resp, 'Mine')
        self.assertNotContains(resp, 'Theirs')

    def test_empty_state(self):
        self.login(self.alice)
        self.assertContains(self.client.get(reverse('closet:my_closet')), 'Your closet is empty')

    def test_search_and_filters(self):
        self.make_item(name='Linen Shirt', size='L', condition='new', status='barter')
        self.make_item(name='Wool Coat', size='M', condition='fair')
        self.login(self.alice)
        url = reverse('closet:my_closet')
        self.assertContains(self.client.get(url, {'q': 'linen'}), 'Linen Shirt')
        self.assertNotContains(self.client.get(url, {'q': 'linen'}), 'Wool Coat')
        self.assertNotContains(self.client.get(url, {'size': 'L'}), 'Wool Coat')
        self.assertNotContains(self.client.get(url, {'condition': 'fair'}), 'Linen Shirt')
        self.assertNotContains(self.client.get(url, {'status': 'barter'}), 'Wool Coat')
        # Nilai filter tidak valid diabaikan, bukan error
        self.assertEqual(self.client.get(url, {'size': 'zzz', 'status': 'zzz'}).status_code, 200)

    def test_pagination(self):
        for i in range(13):
            self.make_item(name=f'Item {i:02d}')
        self.login(self.alice)
        url = reverse('closet:my_closet')
        self.assertEqual(len(self.client.get(url).context['page'].object_list), 12)
        self.assertEqual(len(self.client.get(url, {'page': 2}).context['page'].object_list), 1)


class CreateEditDeleteTests(ClosetTestBase):
    def valid_data(self, **over):
        data = {
            'photo': make_photo(), 'name': 'Blue Shirt', 'size': 'M',
            'condition': 'good', 'status': 'barter', 'description': 'Soft cotton',
        }
        data.update(over)
        return data

    def test_create_sets_owner_from_request(self):
        self.login(self.alice)
        resp = self.client.post(reverse('closet:item_add'), self.valid_data())
        self.assertRedirects(resp, reverse('closet:my_closet'))
        item = Clothing.objects.get()
        self.assertEqual(item.owner, self.alice)
        self.assertEqual(item.status, 'barter')

    def test_create_requires_photo_and_name(self):
        self.login(self.alice)
        resp = self.client.post(reverse('closet:item_add'), self.valid_data(photo='', name='  '))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('photo', resp.context['form'].errors)
        self.assertIn('name', resp.context['form'].errors)
        self.assertEqual(Clothing.objects.count(), 0)

    def test_create_rejects_non_image(self):
        self.login(self.alice)
        bad = SimpleUploadedFile('x.png', b'not an image', content_type='image/png')
        resp = self.client.post(reverse('closet:item_add'), self.valid_data(photo=bad))
        self.assertIn('photo', resp.context['form'].errors)

    def test_form_rejects_oversized_photo(self):
        photo = make_photo()
        photo.size = 6 * 1024 * 1024  # simulasi file > 5 MB
        form = ClothingForm(
            {'name': 'Big', 'size': 'M', 'condition': 'good', 'status': 'personal'},
            {'photo': photo},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('photo', form.errors)

    def test_create_cannot_start_as_swapped(self):
        self.login(self.alice)
        resp = self.client.post(reverse('closet:item_add'), self.valid_data(status='swapped'))
        self.assertIn('status', resp.context['form'].errors)

    def test_create_ignores_owner_in_post(self):
        self.login(self.alice)
        self.client.post(reverse('closet:item_add'), self.valid_data(owner=self.bob.pk))
        self.assertEqual(Clothing.objects.get().owner, self.alice)

    def test_edit_keeps_photo_when_not_replaced(self):
        item = self.make_item()
        old = item.photo.name
        self.login(self.alice)
        data = self.valid_data(name='Renamed')
        del data['photo']
        resp = self.client.post(reverse('closet:item_edit', args=[item.pk]), data)
        self.assertRedirects(resp, reverse('closet:my_closet'))
        item.refresh_from_db()
        self.assertEqual(item.name, 'Renamed')
        self.assertEqual(item.photo.name, old)

    def test_edit_replaces_photo_and_removes_old_file(self):
        item = self.make_item()
        storage, old = item.photo.storage, item.photo.name
        self.login(self.alice)
        self.client.post(
            reverse('closet:item_edit', args=[item.pk]),
            self.valid_data(photo=make_photo('new.png')),
        )
        item.refresh_from_db()
        self.assertNotEqual(item.photo.name, old)
        self.assertTrue(storage.exists(item.photo.name))
        self.assertFalse(storage.exists(old))

    def test_cannot_edit_or_delete_others_item(self):
        item = self.make_item(owner=self.bob)
        self.login(self.alice)
        self.assertEqual(self.client.get(reverse('closet:item_edit', args=[item.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('closet:item_edit', args=[item.pk]), self.valid_data()).status_code, 404)
        self.assertEqual(self.client.post(reverse('closet:item_delete', args=[item.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('closet:item_status', args=[item.pk]), {'status': 'barter'}).status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.name, 'Denim Jacket')

    def test_delete_needs_post(self):
        item = self.make_item()
        self.login(self.alice)
        url = reverse('closet:item_delete', args=[item.pk])
        self.assertContains(self.client.get(url), 'Remove this item?')
        self.assertEqual(Clothing.objects.count(), 1)
        self.assertRedirects(self.client.post(url), reverse('closet:my_closet'))
        self.assertEqual(Clothing.objects.count(), 0)


class StatusTests(ClosetTestBase):
    def test_owner_can_change_status(self):
        item = self.make_item()
        self.login(self.alice)
        resp = self.client.post(
            reverse('closet:item_status', args=[item.pk]),
            {'status': 'top_up', 'next': reverse('closet:my_closet') + '?status=personal'},
        )
        self.assertRedirects(resp, reverse('closet:my_closet') + '?status=personal')
        item.refresh_from_db()
        self.assertEqual(item.status, 'top_up')

    def test_invalid_status_rejected(self):
        item = self.make_item()
        self.login(self.alice)
        self.client.post(reverse('closet:item_status', args=[item.pk]), {'status': 'hacked'})
        item.refresh_from_db()
        self.assertEqual(item.status, 'personal')

    def test_open_redirect_blocked(self):
        item = self.make_item()
        self.login(self.alice)
        resp = self.client.post(
            reverse('closet:item_status', args=[item.pk]),
            {'status': 'barter', 'next': 'https://evil.example.com/'},
        )
        self.assertRedirects(resp, reverse('closet:my_closet'))

    def test_get_not_allowed(self):
        item = self.make_item()
        self.login(self.alice)
        self.assertEqual(self.client.get(reverse('closet:item_status', args=[item.pk])).status_code, 405)


class PublicViewTests(ClosetTestBase):
    def setUp(self):
        super().setUp()
        self.personal = self.make_item(name='Private Piece', status='personal')
        self.offered = self.make_item(name='Offered Piece', status='barter')
        self.swapped = self.make_item(name='Gone Piece', status='swapped')

    def test_guest_sees_only_offered_in_public_closet(self):
        resp = self.client.get(reverse('closet:user_closet', args=['alice']))
        self.assertContains(resp, 'Offered Piece')
        self.assertNotContains(resp, 'Private Piece')
        self.assertNotContains(resp, 'Gone Piece')

    def test_public_closet_unknown_user_404(self):
        self.assertEqual(self.client.get(reverse('closet:user_closet', args=['nobody'])).status_code, 404)

    def test_owner_visiting_own_public_closet_goes_to_my_closet(self):
        self.login(self.alice)
        resp = self.client.get(reverse('closet:user_closet', args=['alice']))
        self.assertRedirects(resp, reverse('closet:my_closet'))

    def test_public_closet_has_no_owner_controls(self):
        self.login(self.bob)
        resp = self.client.get(reverse('closet:user_closet', args=['alice']))
        self.assertNotContains(resp, 'Delete')
        self.assertNotContains(resp, 'data-autosubmit')

    def test_guest_can_view_offered_detail(self):
        resp = self.client.get(self.offered.get_absolute_url())
        self.assertContains(resp, 'Offered Piece')
        self.assertContains(resp, 'Sign in to chat')

    def test_personal_detail_hidden_from_others_but_not_owner(self):
        url = self.personal.get_absolute_url()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.login(self.bob)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.login(self.alice)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_swapped_detail_shows_unavailable_without_chat(self):
        self.login(self.bob)
        resp = self.client.get(self.swapped.get_absolute_url())
        self.assertContains(resp, 'no longer available')
        self.assertNotContains(resp, 'Chat with')

    def test_logged_in_user_gets_chat_form_with_item(self):
        self.login(self.bob)
        resp = self.client.get(self.offered.get_absolute_url())
        self.assertContains(resp, reverse('chat:start', args=[self.alice.pk]))
        self.assertContains(resp, f'name="item_id" value="{self.offered.pk}"')
        self.assertContains(resp, 'name="item_name" value="Offered Piece"')

    def test_owner_sees_edit_delete_on_detail(self):
        self.login(self.alice)
        resp = self.client.get(self.offered.get_absolute_url())
        self.assertContains(resp, reverse('closet:item_edit', args=[self.offered.pk]))
        self.assertNotContains(resp, 'Chat with')

    def test_public_filters(self):
        self.make_item(name='Red Dress', status='donate', size='S')
        url = reverse('closet:user_closet', args=['alice'])
        resp = self.client.get(url, {'size': 'S'})
        self.assertContains(resp, 'Red Dress')
        self.assertNotContains(resp, 'Offered Piece')
