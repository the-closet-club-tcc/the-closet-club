import io
import json
from unittest import mock
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import resolve_url
from django.urls import reverse
from django.test import SimpleTestCase, TestCase, override_settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from .models import Conversation, Message, Attachment, Report, Block
from . import osm
from .views import QUICK_REPLIES
from swap.models import SwapRequest
from .services import ensure_swap_card

User = get_user_model()

class ChatTestBase(TestCase):
    def setUp(self):
        self.burhania = User.objects.create_user('burhania', password='pass12345')
        self.amelia = User.objects.create_user('amelia', password='pass12345')
        self.faizy = User.objects.create_user('faizy', password='pass12345')
        self.conv = Conversation.objects.create(
            user1=self.burhania, user2=self.amelia,
            item_id=1, item_name='Kemeja Linen Krem',
        )
        self.msg_b = Message.objects.create(
            conversation=self.conv, sender=self.burhania, content='Halo',
        )
        self.msg_a = Message.objects.create(
            conversation=self.conv, sender=self.amelia, content='Hai',
        )

    def login(self, user):
        self.assertTrue(self.client.login(username=user.username, password='pass12345'))


class ModelTests(ChatTestBase):
    def test_has_participant(self):
        self.assertTrue(self.conv.has_participant(self.burhania))
        self.assertTrue(self.conv.has_participant(self.amelia))
        self.assertFalse(self.conv.has_participant(self.faizy))

    def test_other_user(self):
        self.assertEqual(self.conv.other_user(self.burhania), self.amelia)
        self.assertEqual(self.conv.other_user(self.amelia), self.burhania)

    def test_str(self):
        self.assertIn('burhania', str(self.conv))
        self.assertIn('Halo', str(self.msg_b))

    def test_messages_ordered_by_created_at(self):
        contents = list(self.conv.messages.values_list('content', flat=True))
        self.assertEqual(contents, ['Halo', 'Hai'])


class AuthTests(ChatTestBase):
    def test_anonymous_redirected_to_login(self):
        urls = [
            reverse('chat:index'),
            reverse('chat:room', args=[self.conv.id]),
            reverse('chat:messages', args=[self.conv.id]),
            reverse('chat:send', args=[self.conv.id]),
            reverse('chat:edit', args=[self.msg_b.id]),
            reverse('chat:delete', args=[self.msg_b.id]),
        ]
        for url in urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, url)
            self.assertIn(resolve_url(settings.LOGIN_URL), resp.url, url)

    def test_non_participant_gets_404_everywhere(self):
        self.login(self.faizy)
        self.assertEqual(self.client.get(reverse('chat:room', args=[self.conv.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse('chat:messages', args=[self.conv.id])).status_code, 404)
        resp = self.client.post(reverse('chat:send', args=[self.conv.id]), {'content': 'intip'})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.conv.messages.count(), 2)


class ChatListTests(ChatTestBase):
    def test_list_shows_only_own_conversations(self):
        other = Conversation.objects.create(user1=self.amelia, user2=self.faizy)
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:index'))
        self.assertEqual(resp.status_code, 200)
        ids = [c['conversation'].id for c in resp.context['conversations']]
        self.assertEqual(ids, [self.conv.id])
        self.assertNotIn(other.id, ids)

    def test_empty_list_for_user_without_conversation(self):
        self.login(self.faizy)
        resp = self.client.get(reverse('chat:index'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['conversations'], [])
        self.assertContains(resp, 'Belum ada percakapan')

    def test_room_shows_messages_and_item(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:room', args=[self.conv.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Halo')
        self.assertContains(resp, 'Hai')
        self.assertContains(resp, 'Kemeja Linen Krem')

    def test_preview_for_location_message(self):
        Message.objects.create(
            conversation=self.conv, sender=self.amelia,
            message_type='location', place_name='Stasiun Depok Baru',
            address='Jl. Margonda Raya, Depok',
            latitude='-6.391000', longitude='106.818000',
        )
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:index'))
        self.assertEqual(
            resp.context['conversations'][0]['preview'],
            'Lokasi: Stasiun Depok Baru',
        )

    def test_preview_for_empty_conversation(self):
        empty = Conversation.objects.create(user1=self.burhania, user2=self.faizy)
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:index'))
        previews = {c['conversation'].id: c['preview'] for c in resp.context['conversations']}
        self.assertEqual(previews[empty.id], 'Belum ada pesan')

    def test_unread_badge_and_mark_read(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:index'))
        self.assertEqual(resp.context['conversations'][0]['unread'], 1)

        self.client.get(reverse('chat:room', args=[self.conv.id]))
        self.msg_a.refresh_from_db()
        self.assertTrue(self.msg_a.is_read)

        resp = self.client.get(reverse('chat:index'))
        self.assertEqual(resp.context['conversations'][0]['unread'], 0)

    def test_own_messages_not_marked_read_by_opening(self):
        self.login(self.burhania)
        self.client.get(reverse('chat:room', args=[self.conv.id]))
        self.msg_b.refresh_from_db()
        self.assertFalse(self.msg_b.is_read)


class SendMessageTests(ChatTestBase):
    def test_send_message(self):
        self.login(self.burhania)
        resp = self.client.post(
            reverse('chat:send', args=[self.conv.id]), {'content': '  Siap, Sabtu ya  '},
        )
        self.assertEqual(resp.status_code, 200)
        msg = self.conv.messages.last()
        self.assertEqual(msg.content, 'Siap, Sabtu ya')
        self.assertEqual(msg.sender, self.burhania)
        self.assertContains(resp, 'Siap, Sabtu ya')

    def test_empty_message_not_saved(self):
        self.login(self.burhania)
        self.client.post(reverse('chat:send', args=[self.conv.id]), {'content': '   '})
        self.assertEqual(self.conv.messages.count(), 2)

    def test_message_truncated_to_2000_chars(self):
        self.login(self.burhania)
        self.client.post(reverse('chat:send', args=[self.conv.id]), {'content': 'a' * 3000})
        self.assertEqual(len(self.conv.messages.last().content), 2000)

    def test_send_requires_post(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:send', args=[self.conv.id]))
        self.assertEqual(resp.status_code, 405)

    def test_messages_partial(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:messages', args=[self.conv.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Halo')
        self.assertTemplateUsed(resp, 'chat/_messages.html')


class EditMessageTests(ChatTestBase):
    def test_get_edit_form(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:edit', args=[self.msg_b.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'chat/_edit_form.html')

    def test_edit_own_message(self):
        self.login(self.burhania)
        resp = self.client.post(reverse('chat:edit', args=[self.msg_b.id]), {'content': 'Halo lagi'})
        self.assertEqual(resp.status_code, 200)
        self.msg_b.refresh_from_db()
        self.assertEqual(self.msg_b.content, 'Halo lagi')
        self.assertTrue(self.msg_b.is_edited)

    def test_edit_with_same_content_not_marked_edited(self):
        self.login(self.burhania)
        self.client.post(reverse('chat:edit', args=[self.msg_b.id]), {'content': 'Halo'})
        self.msg_b.refresh_from_db()
        self.assertFalse(self.msg_b.is_edited)

    def test_edit_with_empty_content_ignored(self):
        self.login(self.burhania)
        self.client.post(reverse('chat:edit', args=[self.msg_b.id]), {'content': '  '})
        self.msg_b.refresh_from_db()
        self.assertEqual(self.msg_b.content, 'Halo')
        self.assertFalse(self.msg_b.is_edited)

    def test_cannot_edit_others_message(self):
        self.login(self.amelia)
        resp = self.client.post(reverse('chat:edit', args=[self.msg_b.id]), {'content': 'hack'})
        self.assertEqual(resp.status_code, 404)
        self.msg_b.refresh_from_db()
        self.assertEqual(self.msg_b.content, 'Halo')

    def test_cannot_edit_location_message(self):
        loc = Message.objects.create(
            conversation=self.conv, sender=self.burhania,
            message_type='location', place_name='Stasiun Depok Baru',
        )
        self.login(self.burhania)
        resp = self.client.post(reverse('chat:edit', args=[loc.id]), {'content': 'x'})
        self.assertEqual(resp.status_code, 404)


class DeleteMessageTests(ChatTestBase):
    def test_delete_own_message(self):
        self.login(self.burhania)
        resp = self.client.post(reverse('chat:delete', args=[self.msg_b.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Message.objects.filter(pk=self.msg_b.id).exists())

    def test_cannot_delete_others_message(self):
        self.login(self.amelia)
        resp = self.client.post(reverse('chat:delete', args=[self.msg_b.id]))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Message.objects.filter(pk=self.msg_b.id).exists())

    def test_non_participant_cannot_delete(self):
        self.login(self.faizy)
        resp = self.client.post(reverse('chat:delete', args=[self.msg_b.id]))
        self.assertEqual(resp.status_code, 404)

    def test_delete_requires_post(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:delete', args=[self.msg_b.id]))
        self.assertEqual(resp.status_code, 405)

    def test_delete_own_location_message(self):
        loc = Message.objects.create(
            conversation=self.conv, sender=self.burhania,
            message_type='location', place_name='Stasiun Depok Baru',
        )
        self.login(self.burhania)
        self.client.post(reverse('chat:delete', args=[loc.id]))
        self.assertFalse(Message.objects.filter(pk=loc.id).exists())

class StartConversationTests(ChatTestBase):
    def test_start_creates_conversation(self):
        self.login(self.faizy)
        resp = self.client.post(reverse('chat:start', args=[self.amelia.id]))
        conv = Conversation.objects.get(user1=self.faizy, user2=self.amelia)
        self.assertRedirects(resp, reverse('chat:room', args=[conv.id]))

    def test_start_reuses_existing_conversation(self):
        self.login(self.amelia)
        resp = self.client.post(reverse('chat:start', args=[self.burhania.id]))
        self.assertRedirects(resp, reverse('chat:room', args=[self.conv.id]))
        self.assertEqual(Conversation.objects.count(), 1)

    def test_cannot_start_chat_with_self(self):
        self.login(self.burhania)
        resp = self.client.post(reverse('chat:start', args=[self.burhania.id]))
        self.assertRedirects(resp, reverse('chat:index'))
        self.assertEqual(Conversation.objects.count(), 1)

    def test_start_stores_item(self):
        self.login(self.faizy)
        self.client.post(
            reverse('chat:start', args=[self.amelia.id]),
            {'item_id': '7', 'item_name': 'Rok Midi Olive'},
        )
        conv = Conversation.objects.get(user1=self.faizy, user2=self.amelia)
        self.assertEqual(conv.item_id, 7)
        self.assertEqual(conv.item_name, 'Rok Midi Olive')

    def test_start_requires_post_and_login(self):
        self.assertEqual(self.client.post(reverse('chat:start', args=[self.amelia.id])).status_code, 302)
        self.login(self.burhania)
        self.assertEqual(self.client.get(reverse('chat:start', args=[self.amelia.id])).status_code, 405)

class LocationTests(ChatTestBase):
    def test_place_search_uses_osm(self):
        fake = [{'name': 'Stasiun Depok Baru', 'address': 'Jl. Margonda Raya, Depok',
                 'lat': -6.391, 'lon': 106.818}]
        self.login(self.burhania)
        with mock.patch('chat.views.search_places', return_value=fake) as m:
            resp = self.client.get(
                reverse('chat:places', args=[self.conv.id]),
                {'q': 'depok', 'category': 'stasiun'},
            )
        m.assert_called_once_with('depok', 'stasiun')
        self.assertContains(resp, 'Stasiun Depok Baru')

    def test_place_search_without_query_skips_osm(self):
        self.login(self.burhania)
        with mock.patch('chat.views.search_places') as m:
            resp = self.client.get(reverse('chat:places', args=[self.conv.id]))
        m.assert_not_called()
        self.assertEqual(resp.status_code, 200)

    def test_place_search_no_results_message(self):
        self.login(self.burhania)
        with mock.patch('chat.views.search_places', return_value=[]):
            resp = self.client.get(reverse('chat:places', args=[self.conv.id]), {'q': 'zzz'})
        self.assertContains(resp, 'Tempat tidak ditemukan')

    def test_place_search_non_participant_404(self):
        self.login(self.faizy)
        resp = self.client.get(reverse('chat:places', args=[self.conv.id]), {'q': 'depok'})
        self.assertEqual(resp.status_code, 404)

    def test_send_location_creates_message(self):
        self.login(self.burhania)
        resp = self.client.post(reverse('chat:send_location', args=[self.conv.id]), {
            'name': 'Stasiun Depok Baru', 'address': 'Jl. Margonda Raya, Depok',
            'lat': '-6.391000', 'lon': '106.818000',
        })
        self.assertEqual(resp.status_code, 200)
        msg = self.conv.messages.last()
        self.assertEqual(msg.message_type, 'location')
        self.assertEqual(msg.place_name, 'Stasiun Depok Baru')
        self.assertEqual(msg.latitude, Decimal('-6.391000'))
        self.assertEqual(msg.sender, self.burhania)

    def test_send_location_rejects_invalid_coordinates(self):
        self.login(self.burhania)
        for lat, lon in [('abc', '106.8'), ('999', '106.8'), ('-6.3', '999'), ('nan', '1')]:
            resp = self.client.post(reverse('chat:send_location', args=[self.conv.id]),
                                    {'name': 'X', 'lat': lat, 'lon': lon})
            self.assertEqual(resp.status_code, 400, (lat, lon))
        self.assertEqual(self.conv.messages.count(), 2)

    def test_send_location_requires_name(self):
        self.login(self.burhania)
        resp = self.client.post(reverse('chat:send_location', args=[self.conv.id]),
                                {'name': ' ', 'lat': '-6.3', 'lon': '106.8'})
        self.assertEqual(resp.status_code, 400)

    def test_send_location_requires_post(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:send_location', args=[self.conv.id]))
        self.assertEqual(resp.status_code, 405)

    def test_send_location_non_participant_404(self):
        self.login(self.faizy)
        resp = self.client.post(reverse('chat:send_location', args=[self.conv.id]),
                                {'name': 'X', 'lat': '-6.3', 'lon': '106.8'})
        self.assertEqual(resp.status_code, 404)

    def test_free_text_search_without_category(self):
            self.login(self.burhania)
            with mock.patch('chat.views.search_places', return_value=[]) as m:
                self.client.get(
                    reverse('chat:places', args=[self.conv.id]),
                    {'q': 'fakultas ilmu komputer universitas indonesia'},
                )
            m.assert_called_once_with('fakultas ilmu komputer universitas indonesia', '')    


def _fake_response(payload):
    resp = mock.MagicMock()
    resp.read.return_value = json.dumps(payload).encode('utf-8')
    resp.__enter__.return_value = resp
    return resp


class OsmTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_second_identical_search_uses_cache(self):
        payload = [{'name': 'Fasilkom UI', 'display_name': 'Fasilkom UI, Depok',
                    'lat': '-6.36', 'lon': '106.82'}]
        with mock.patch('chat.osm.urllib.request.urlopen',
                        return_value=_fake_response(payload)) as m:
            first = osm.search_places('Fasilkom UI')
            second = osm.search_places('fasilkom ui')
        self.assertEqual(first, second)
        self.assertEqual(m.call_count, 1)

    def test_network_error_is_not_cached(self):
        with mock.patch('chat.osm.urllib.request.urlopen', side_effect=OSError):
            self.assertEqual(osm.search_places('depok'), [])
        payload = [{'name': 'Depok', 'lat': '-6.4', 'lon': '106.8'}]
        with mock.patch('chat.osm.urllib.request.urlopen',
                        return_value=_fake_response(payload)):
            self.assertEqual(len(osm.search_places('depok')), 1)    

    def test_parses_results_and_sets_user_agent(self):
        payload = [{'name': 'Stasiun Depok Baru', 'display_name': 'Stasiun Depok Baru, Depok',
                    'lat': '-6.3910001', 'lon': '106.8180002'}]
        with mock.patch('chat.osm.urllib.request.urlopen',
                        return_value=_fake_response(payload)) as m:
            results = osm.search_places('depok', 'stasiun')
        self.assertEqual(results, [{
            'name': 'Stasiun Depok Baru', 'address': 'Stasiun Depok Baru, Depok',
            'lat': -6.391, 'lon': 106.818,
        }])
        req = m.call_args[0][0]
        self.assertIn('q=stasiun+depok', req.full_url)
        self.assertIn('TheClosetClub', req.get_header('User-agent'))

    def test_network_error_returns_empty_list(self):
        with mock.patch('chat.osm.urllib.request.urlopen', side_effect=OSError):
            self.assertEqual(osm.search_places('depok'), [])

    def test_empty_query_makes_no_request(self):
        with mock.patch('chat.osm.urllib.request.urlopen') as m:
            self.assertEqual(osm.search_places('   '), [])
        m.assert_not_called()

    def test_skips_items_with_bad_coordinates(self):
        payload = [{'name': 'A', 'lat': 'x', 'lon': '1'}, {'name': 'B'}]
        with mock.patch('chat.osm.urllib.request.urlopen',
                        return_value=_fake_response(payload)):
            self.assertEqual(osm.search_places('depok'), [])

    def test_prefixes_category_and_shortens_address(self):
        payload = [{
            'name': 'Depok',
            'display_name': 'Depok, Jalan Stasiun Depok Lama, Pancoran Mas, Depok, Jawa Barat, 16436, Indonesia',
            'lat': '-6.40', 'lon': '106.81',
        }]
        with mock.patch('chat.osm.urllib.request.urlopen',
                        return_value=_fake_response(payload)):
            results = osm.search_places('depok', 'stasiun')
        self.assertEqual(results[0]['name'], 'Stasiun Depok')
        self.assertEqual(
            results[0]['address'],
            'Depok, Jalan Stasiun Depok Lama, Pancoran Mas, Depok, Jawa Barat',
        )

def _png_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (40, 40), 'red').save(buf, 'PNG')
    return buf.getvalue()

class AttachmentTests(ChatTestBase):
    def _send(self, upload, user=None):
        self.login(user or self.burhania)
        return self.client.post(
            reverse('chat:send_attachment', args=[self.conv.id]), {'file': upload},
        )

    def test_upload_image_is_normalized_to_jpeg(self):
        resp = self._send(SimpleUploadedFile('foto.png', _png_bytes(), content_type='image/png'))
        self.assertEqual(resp.status_code, 200)
        msg = self.conv.messages.last()
        self.assertEqual(msg.message_type, 'image')
        self.assertEqual(msg.attachment_type, 'image/jpeg')
        self.assertTrue(msg.attachment_name.endswith('.jpg'))
        self.assertTrue(Attachment.objects.filter(message=msg).exists())

    def test_fake_image_rejected(self):
        resp = self._send(SimpleUploadedFile('palsu.png', b'bukan gambar', content_type='image/png'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.conv.messages.count(), 2)

    def test_upload_document(self):
        resp = self._send(SimpleUploadedFile('surat.pdf', b'%PDF-1.4 tes', content_type='application/pdf'))
        self.assertEqual(resp.status_code, 200)
        msg = self.conv.messages.last()
        self.assertEqual(msg.message_type, 'file')
        self.assertEqual(msg.attachment_name, 'surat.pdf')
        self.assertEqual(msg.attachment_size, len(b'%PDF-1.4 tes'))

    def test_unsupported_type_rejected(self):
        resp = self._send(SimpleUploadedFile('virus.exe', b'MZ', content_type='application/octet-stream'))
        self.assertEqual(resp.status_code, 400)

    def test_document_too_large_rejected(self):
        with mock.patch('chat.views.MAX_UPLOAD', 10):
            resp = self._send(SimpleUploadedFile('surat.pdf', b'x' * 50, content_type='application/pdf'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.conv.messages.count(), 2)

    def test_image_too_large_rejected(self):
        with mock.patch('chat.views.MAX_UPLOAD', 10):
            resp = self._send(SimpleUploadedFile('foto.png', _png_bytes(), content_type='image/png'))
        self.assertEqual(resp.status_code, 400)

    def test_no_file_rejected(self):
        self.login(self.burhania)
        resp = self.client.post(reverse('chat:send_attachment', args=[self.conv.id]))
        self.assertEqual(resp.status_code, 400)

    def test_non_participant_cannot_upload(self):
        resp = self._send(SimpleUploadedFile('surat.pdf', b'%PDF', content_type='application/pdf'),
                          user=self.faizy)
        self.assertEqual(resp.status_code, 404)

    def test_serve_image_inline_and_document_as_download(self):
        self._send(SimpleUploadedFile('foto.png', _png_bytes(), content_type='image/png'))
        img = self.conv.messages.last()
        self._send(SimpleUploadedFile('surat.pdf', b'%PDF-1.4 tes', content_type='application/pdf'))
        doc = self.conv.messages.last()

        r = self.client.get(reverse('chat:attachment', args=[img.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'image/jpeg')
        self.assertTrue(r['Content-Disposition'].startswith('inline'))
        self.assertEqual(r['X-Content-Type-Options'], 'nosniff')

        r = self.client.get(reverse('chat:attachment', args=[doc.id]))
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r['Content-Disposition'].startswith('attachment'))

    def test_non_participant_cannot_download(self):
        self._send(SimpleUploadedFile('surat.pdf', b'%PDF', content_type='application/pdf'))
        doc = self.conv.messages.last()
        self.client.logout()
        self.login(self.faizy)
        r = self.client.get(reverse('chat:attachment', args=[doc.id]))
        self.assertEqual(r.status_code, 404)

    def test_deleting_message_removes_attachment(self):
        self._send(SimpleUploadedFile('surat.pdf', b'%PDF', content_type='application/pdf'))
        doc = self.conv.messages.last()
        self.client.post(reverse('chat:delete', args=[doc.id]))
        self.assertFalse(Attachment.objects.filter(message_id=doc.id).exists())

    def test_list_preview_for_attachments(self):
        self._send(SimpleUploadedFile('surat.pdf', b'%PDF', content_type='application/pdf'))
        resp = self.client.get(reverse('chat:index'))
        self.assertEqual(resp.context['conversations'][0]['preview'], 'Dokumen: surat.pdf')

    def test_list_preview_for_image_attachment(self):
        self._send(SimpleUploadedFile('foto.png', _png_bytes(), content_type='image/png'))
        resp = self.client.get(reverse('chat:index'))
        self.assertEqual(resp.context['conversations'][0]['preview'], 'Foto')

    def test_unsupported_image_format_rejected(self):
        buf = io.BytesIO()
        Image.new('RGB', (10, 10)).save(buf, 'BMP')
        resp = self._send(SimpleUploadedFile('foto.png', buf.getvalue(), content_type='image/png'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.conv.messages.count(), 2)

    def test_invalid_filename_rejected(self):
        resp = self._send(SimpleUploadedFile('###', b'data'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.conv.messages.count(), 2)

    def test_upload_jpeg_is_resized(self):
        buf = io.BytesIO()
        Image.new('RGB', (3000, 2000), 'blue').save(buf, 'JPEG')
        resp = self._send(SimpleUploadedFile('foto.jpg', buf.getvalue(), content_type='image/jpeg'))
        self.assertEqual(resp.status_code, 200)
        msg = self.conv.messages.last()
        self.assertEqual(msg.message_type, 'image')
        self.assertEqual(msg.attachment_type, 'image/jpeg')
        saved = Image.open(io.BytesIO(bytes(msg.attachment.data)))
        self.assertLessEqual(max(saved.size), 1280)

class UserSearchTests(ChatTestBase):
    def test_excludes_self_and_filters(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:user_search'), {'q': 'amel'})
        self.assertEqual([u.username for u in resp.context['new_users']], ['amelia'])
        resp = self.client.get(reverse('chat:user_search'))
        names = [u.username for u in resp.context['new_users']]
        self.assertNotIn('burhania', names)
        self.assertIn('faizy', names)

    def test_no_match_message(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:user_search'), {'q': 'zzzz'})
        self.assertContains(resp, 'Tidak ada pengguna dengan nama itu')

    def test_requires_login(self):
        self.assertEqual(self.client.get(reverse('chat:user_search')).status_code, 302)


class ConversationListPartialTests(ChatTestBase):
    def test_partial_shows_own_conversations(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:conversation_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'chat/_conversation_list.html')
        self.assertContains(resp, 'amelia')

    def test_active_conversation_has_no_unread_badge(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:conversation_list'), {'active': self.conv.id})
        self.assertEqual(resp.context['conversations'][0]['unread'], 0)
        resp = self.client.get(reverse('chat:conversation_list'))
        self.assertEqual(resp.context['conversations'][0]['unread'], 1)

    def test_requires_login(self):
        self.assertEqual(self.client.get(reverse('chat:conversation_list')).status_code, 302)


class DeleteConversationTests(ChatTestBase):
    def test_delete_hides_conversation_for_that_user_only(self):
        self.login(self.burhania)
        resp = self.client.post(reverse('chat:delete_conversation', args=[self.conv.id]))
        self.assertRedirects(resp, reverse('chat:index') + '?deleted=1')
        self.assertEqual(self.client.get(reverse('chat:index')).context['conversations'], [])
        self.client.logout()
        self.login(self.amelia)
        self.assertEqual(len(self.client.get(reverse('chat:index')).context['conversations']), 1)
        self.assertEqual(self.conv.messages.count(), 2)

    def test_conversation_returns_with_only_new_messages(self):
        self.login(self.burhania)
        self.client.post(reverse('chat:delete_conversation', args=[self.conv.id]))
        Message.objects.create(conversation=self.conv, sender=self.amelia, content='Halo lagi')
        resp = self.client.get(reverse('chat:room', args=[self.conv.id]))
        self.assertEqual([m.content for m in resp.context['chat_messages']], ['Halo lagi'])
        self.assertEqual(len(resp.context['conversations']), 1)

    def test_non_participant_gets_404(self):
        self.login(self.faizy)
        resp = self.client.post(reverse('chat:delete_conversation', args=[self.conv.id]))
        self.assertEqual(resp.status_code, 404)

    def test_requires_post(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:delete_conversation', args=[self.conv.id]))
        self.assertEqual(resp.status_code, 405)


class MessageLimitTests(ChatTestBase):
    def test_only_latest_200_messages_are_shown(self):
        Message.objects.bulk_create([
            Message(conversation=self.conv, sender=self.amelia, content=f'pesan {i}')
            for i in range(250)
        ])
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:room', args=[self.conv.id]))
        shown = resp.context['chat_messages']
        self.assertEqual(len(shown), 200)
        self.assertEqual(shown[0].content, 'pesan 50')
        self.assertEqual(shown[-1].content, 'pesan 249')

class ReplyTests(ChatTestBase):
    def _send(self, **data):
        return self.client.post(reverse('chat:send', args=[self.conv.id]), data)

    def test_reply_links_to_original_message(self):
        target = Message.objects.create(
            conversation=self.conv, sender=self.amelia, content='Kemeja masih ada',
        )
        self.login(self.burhania)
        resp = self._send(content='Boleh, aku ambil', reply_to=str(target.id))
        self.assertEqual(resp.status_code, 200)
        msg = self.conv.messages.last()
        self.assertEqual(msg.reply_to_id, target.id)
        self.assertTrue(msg.has_reply)
        self.assertEqual(resp.context['chat_messages'][-1].reply_to_id, target.id)

    def test_reply_to_message_in_other_conversation_is_ignored(self):
        other = Conversation.objects.create(user1=self.amelia, user2=self.faizy)
        foreign = Message.objects.create(conversation=other, sender=self.amelia, content='rahasia')
        self.login(self.burhania)
        self._send(content='halo', reply_to=str(foreign.id))
        msg = self.conv.messages.last()
        self.assertIsNone(msg.reply_to)
        self.assertFalse(msg.has_reply)

    def test_non_numeric_reply_to_is_ignored(self):
        self.login(self.burhania)
        self._send(content='halo', reply_to='abc')
        msg = self.conv.messages.last()
        self.assertIsNone(msg.reply_to)
        self.assertFalse(msg.has_reply)

    def test_deleted_original_shows_unavailable(self):
        self.login(self.amelia)
        self._send(content='Setuju', reply_to=str(self.msg_b.id))
        self.client.logout()
        self.login(self.burhania)
        self.client.post(reverse('chat:delete', args=[self.msg_b.id]))
        reply = self.conv.messages.last()
        reply.refresh_from_db()
        self.assertIsNone(reply.reply_to)
        self.assertTrue(reply.has_reply)
        resp = self.client.get(reverse('chat:messages', args=[self.conv.id]))
        self.assertContains(resp, 'Pesan asli tidak tersedia')


class QuickReplyTests(ChatTestBase):
    def test_quick_replies_shown_in_room(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:room', args=[self.conv.id]))
        self.assertEqual(resp.context['quick_replies'], QUICK_REPLIES)
        for text in QUICK_REPLIES:
            self.assertContains(resp, text)

    def test_quick_reply_is_sent_as_plain_message(self):
        self.login(self.burhania)
        self.client.post(reverse('chat:send', args=[self.conv.id]), {'content': QUICK_REPLIES[0]})
        msg = self.conv.messages.last()
        self.assertEqual(msg.content, QUICK_REPLIES[0])
        self.assertFalse(msg.has_reply)


class PreviewTextTests(ChatTestBase):
    def test_preview_text_per_type(self):
        loc = Message(message_type='location', place_name='Stasiun Depok')
        img = Message(message_type='image')
        doc = Message(message_type='file', attachment_name='surat.pdf')
        self.assertEqual(loc.preview_text(), 'Lokasi: Stasiun Depok')
        self.assertEqual(img.preview_text(), 'Foto')
        self.assertEqual(doc.preview_text(), 'Dokumen: surat.pdf')
        self.assertEqual(self.msg_b.preview_text(), 'Halo')

class BlockTests(ChatTestBase):
    def _block(self, user=None):
        self.login(user or self.burhania)
        return self.client.post(reverse('chat:block', args=[self.conv.id]))

    def test_block_creates_block_and_redirects(self):
        resp = self._block()
        self.assertRedirects(resp, reverse('chat:room', args=[self.conv.id]) + '?blocked=1')
        self.assertTrue(Block.objects.filter(blocker=self.burhania, blocked=self.amelia).exists())

    def test_block_twice_creates_one_block(self):
        self._block()
        self._block()
        self.assertEqual(Block.objects.count(), 1)

    def test_block_non_participant_404_and_get_405(self):
        self.assertEqual(self._block(self.faizy).status_code, 404)
        self.login(self.burhania)
        self.assertEqual(self.client.get(reverse('chat:block', args=[self.conv.id])).status_code, 405)

    def test_blocked_user_cannot_send_anything(self):
        Block.objects.create(blocker=self.burhania, blocked=self.amelia)
        self.login(self.amelia)
        resp = self.client.post(reverse('chat:send', args=[self.conv.id]), {'content': 'halo'})
        self.assertEqual(resp.status_code, 403)
        self.assertIn('tidak dapat mengirim pesan', resp.content.decode())
        resp = self.client.post(reverse('chat:send_location', args=[self.conv.id]),
                                {'name': 'X', 'lat': '-6.3', 'lon': '106.8'})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post(reverse('chat:send_attachment', args=[self.conv.id]),
                                {'file': SimpleUploadedFile('s.pdf', b'%PDF', content_type='application/pdf')})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.conv.messages.count(), 2)

    def test_blocker_cannot_send_until_unblocked(self):
        Block.objects.create(blocker=self.burhania, blocked=self.amelia)
        self.login(self.burhania)
        url = reverse('chat:send', args=[self.conv.id])
        resp = self.client.post(url, {'content': 'halo'})
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Buka blokir untuk mengirim pesan', resp.content.decode())
        resp = self.client.post(reverse('chat:unblock', args=[self.conv.id]))
        self.assertRedirects(resp, reverse('chat:room', args=[self.conv.id]) + '?unblocked=1')
        self.assertEqual(self.client.post(url, {'content': 'halo'}).status_code, 200)

    def test_unblock_non_participant_404_and_get_405(self):
        self.login(self.faizy)
        self.assertEqual(self.client.post(reverse('chat:unblock', args=[self.conv.id])).status_code, 404)
        self.client.logout()
        self.login(self.burhania)
        self.assertEqual(self.client.get(reverse('chat:unblock', args=[self.conv.id])).status_code, 405)

    def test_room_shows_blocked_state(self):
        Block.objects.create(blocker=self.burhania, blocked=self.amelia)
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:room', args=[self.conv.id]))
        self.assertTrue(resp.context['blocked_by_me'])
        self.assertContains(resp, 'Buka blokir')
        self.assertNotContains(resp, 'id="message-form"')
        self.client.logout()
        self.login(self.amelia)
        resp = self.client.get(reverse('chat:room', args=[self.conv.id]))
        self.assertTrue(resp.context['blocked_me'])
        self.assertContains(resp, 'tidak dapat mengirim pesan')

    def test_cannot_start_when_blocked_either_way(self):
        Block.objects.create(blocker=self.faizy, blocked=self.burhania)
        self.login(self.burhania)
        resp = self.client.post(reverse('chat:start', args=[self.faizy.id]))
        self.assertRedirects(resp, reverse('chat:index') + '?cannot_start=1')
        Block.objects.all().delete()
        Block.objects.create(blocker=self.burhania, blocked=self.faizy)
        resp = self.client.post(reverse('chat:start', args=[self.faizy.id]))
        self.assertRedirects(resp, reverse('chat:index') + '?cannot_start=1')
        self.assertFalse(Conversation.objects.filter(user1=self.burhania, user2=self.faizy).exists())

    def test_blocked_users_hidden_from_search(self):
        Block.objects.create(blocker=self.burhania, blocked=self.faizy)
        Block.objects.create(blocker=self.amelia, blocked=self.burhania)
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:user_search'))
        self.assertEqual(list(resp.context['new_users']), [])


class ReportTests(ChatTestBase):
    def _report(self, **data):
        return self.client.post(reverse('chat:report', args=[self.conv.id]), data)

    def test_report_user(self):
        self.login(self.burhania)
        resp = self._report(reason='spam', detail='  iklan terus  ')
        self.assertEqual(resp.status_code, 204)
        obj = Report.objects.get()
        self.assertEqual((obj.reporter, obj.reported_user, obj.reason), (self.burhania, self.amelia, 'spam'))
        self.assertEqual(obj.detail, 'iklan terus')
        self.assertIsNone(obj.message)

    def test_report_message_keeps_excerpt_after_deletion(self):
        self.login(self.burhania)
        resp = self._report(reason='penipuan', message_id=str(self.msg_a.id))
        self.assertEqual(resp.status_code, 204)
        obj = Report.objects.get()
        self.assertEqual(obj.message, self.msg_a)
        self.assertEqual(obj.message_excerpt, 'Hai')
        self.msg_a.delete()
        obj.refresh_from_db()
        self.assertIsNone(obj.message)
        self.assertEqual(obj.message_excerpt, 'Hai')

    def test_reason_required_and_validated(self):
        self.login(self.burhania)
        for data in ({}, {'reason': 'xyz'}):
            resp = self._report(**data)
            self.assertEqual(resp.status_code, 400)
            self.assertIn('Pilih alasan laporan', resp.content.decode())
        self.assertEqual(Report.objects.count(), 0)

    def test_other_reason_needs_detail(self):
        self.login(self.burhania)
        resp = self._report(reason='lainnya')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Jelaskan laporanmu', resp.content.decode())
        self.assertEqual(self._report(reason='lainnya', detail='perilaku aneh').status_code, 204)

    def test_detail_too_long(self):
        self.login(self.burhania)
        resp = self._report(reason='spam', detail='a' * 501)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('maksimal 500 karakter', resp.content.decode())

    def test_cannot_report_own_message_or_foreign_message_or_bad_id(self):
        other = Conversation.objects.create(user1=self.amelia, user2=self.faizy)
        foreign = Message.objects.create(conversation=other, sender=self.amelia, content='x')
        self.login(self.burhania)
        for bad in (str(self.msg_b.id), str(foreign.id), 'abc'):
            resp = self._report(reason='spam', message_id=bad)
            self.assertEqual(resp.status_code, 400, bad)
        self.assertEqual(Report.objects.count(), 0)

    def test_access_rules(self):
        self.assertEqual(self._report(reason='spam').status_code, 302)
        self.login(self.faizy)
        self.assertEqual(self._report(reason='spam').status_code, 404)
        self.client.logout()
        self.login(self.burhania)
        self.assertEqual(self.client.get(reverse('chat:report', args=[self.conv.id])).status_code, 405)


class MessageRequestTests(ChatTestBase):
    def _pending(self):
        return Conversation.objects.create(user1=self.faizy, user2=self.amelia, accepted=False)

    def test_existing_conversations_are_accepted(self):
        self.assertTrue(self.conv.accepted)

    def test_new_chat_starts_as_request(self):
        self.login(self.faizy)
        self.client.post(reverse('chat:start', args=[self.amelia.id]))
        self.assertFalse(Conversation.objects.get(user1=self.faizy, user2=self.amelia).accepted)

    def test_banner_only_for_recipient(self):
        conv = self._pending()
        self.login(self.amelia)
        resp = self.client.get(reverse('chat:room', args=[conv.id]))
        self.assertTrue(resp.context['is_request'])
        self.assertContains(resp, 'baru menghubungimu')
        self.client.logout()
        self.login(self.faizy)
        resp = self.client.get(reverse('chat:room', args=[conv.id]))
        self.assertFalse(resp.context['is_request'])
        self.assertNotContains(resp, 'baru menghubungimu')

    def test_recipient_reply_accepts_but_initiator_message_does_not(self):
        conv = self._pending()
        self.login(self.faizy)
        self.client.post(reverse('chat:send', args=[conv.id]), {'content': 'halo'})
        conv.refresh_from_db()
        self.assertFalse(conv.accepted)
        self.client.logout()
        self.login(self.amelia)
        self.client.post(reverse('chat:send', args=[conv.id]), {'content': 'hai'})
        conv.refresh_from_db()
        self.assertTrue(conv.accepted)

    def test_accept_view(self):
        conv = self._pending()
        self.login(self.amelia)
        resp = self.client.post(reverse('chat:accept', args=[conv.id]))
        self.assertRedirects(resp, reverse('chat:room', args=[conv.id]) + '?accepted=1')
        conv.refresh_from_db()
        self.assertTrue(conv.accepted)

    def test_initiator_cannot_accept_own_request(self):
        conv = self._pending()
        self.login(self.faizy)
        resp = self.client.post(reverse('chat:accept', args=[conv.id]))
        self.assertRedirects(resp, reverse('chat:room', args=[conv.id]))
        conv.refresh_from_db()
        self.assertFalse(conv.accepted)

    def test_accept_non_participant_404_and_get_405(self):
        conv = self._pending()
        self.login(self.burhania)
        self.assertEqual(self.client.post(reverse('chat:accept', args=[conv.id])).status_code, 404)
        self.client.logout()
        self.login(self.amelia)
        self.assertEqual(self.client.get(reverse('chat:accept', args=[conv.id])).status_code, 405)

class SafetyBannerTests(ChatTestBase):
    def test_banner_text_shown_in_room(self):
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:room', args=[self.conv.id]))
        self.assertContains(resp, 'Bertemu di tempat umum, jangan transfer sebelum barang diterima')

class SwapCardServiceTests(ChatTestBase):
    def test_ensure_swap_card_creates_only_one_card(self):
        proposal = SwapRequest.objects.create(
            sender=self.burhania,
            recipient=self.amelia,
        )

        first = ensure_swap_card(self.conv, proposal)
        second = ensure_swap_card(self.conv, proposal)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.conversation_id, self.conv.pk)
        self.assertEqual(first.sender_id, self.burhania.pk)
        self.assertEqual(first.message_type, Message.MessageType.SWAP)
        self.assertEqual(
            Message.objects.filter(
                swap_request=proposal,
                message_type=Message.MessageType.SWAP,
            ).count(),
            1,
        )


class SwapActionTests(ChatTestBase):
    def create_pending_request(self, sender=None, recipient=None):
        return SwapRequest.objects.create(
            sender=sender or self.burhania,
            recipient=recipient or self.amelia,
            status=SwapRequest.Status.PENDING,
        )

    def test_non_participant_cannot_use_swap_action(self):
        proposal = self.create_pending_request()
        self.login(self.faizy)

        response = self.client.post(
            reverse(
                'chat:swap_action',
                args=[self.conv.pk, proposal.pk, 'decline'],
            )
        )

        self.assertEqual(response.status_code, 404)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

    def test_request_from_another_pair_cannot_be_used_in_this_chat(self):
        proposal = self.create_pending_request(
            sender=self.faizy,
            recipient=self.amelia,
        )
        self.login(self.amelia)

        response = self.client.post(
            reverse(
                'chat:swap_action',
                args=[self.conv.pk, proposal.pk, 'decline'],
            )
        )

        self.assertEqual(response.status_code, 404)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

    def test_blocked_pair_cannot_accept_pending_request(self):
        from .models import Block

        proposal = self.create_pending_request()
        Block.objects.create(
            blocker=self.burhania,
            blocked=self.amelia,
        )
        self.login(self.amelia)

        response = self.client.post(
            reverse(
                'chat:swap_action',
                args=[self.conv.pk, proposal.pk, 'accept'],
            )
        )

        self.assertEqual(response.status_code, 403)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

    def test_declining_request_updates_status_and_chat(self):
        proposal = self.create_pending_request()
        self.login(self.amelia)

        response = self.client.post(
            reverse(
                'chat:swap_action',
                args=[self.conv.pk, proposal.pk, 'decline'],
            ),
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.DECLINED)

        self.assertTrue(
            Message.objects.filter(
                conversation=self.conv,
                sender=self.amelia,
                message_type=Message.MessageType.TEXT,
                content='Swap request declined.',
            ).exists()
        )
        self.assertContains(response, 'Swap request declined.')

class SwapCardGuardTests(ChatTestBase):
    def make_card(self, status=SwapRequest.Status.PENDING):
        proposal = SwapRequest.objects.create(
            sender=self.burhania, recipient=self.amelia, status=status,
        )
        card = ensure_swap_card(self.conv, proposal)
        return proposal, card

    def test_swap_card_cannot_be_deleted(self):
        _, card = self.make_card()
        self.login(self.burhania)  # pengirim kartu pun tidak boleh menghapus
        resp = self.client.post(reverse('chat:delete', args=[card.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Message.objects.filter(pk=card.pk).exists())

    def test_swap_card_cannot_be_edited(self):
        _, card = self.make_card()
        self.login(self.burhania)
        resp = self.client.get(reverse('chat:edit', args=[card.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_swap_action_requires_post(self):
        proposal, _ = self.make_card()
        self.login(self.amelia)
        resp = self.client.get(
            reverse('chat:swap_action', args=[self.conv.pk, proposal.pk, 'decline']),
        )
        self.assertEqual(resp.status_code, 405)

    def test_unknown_swap_action_is_rejected(self):
        proposal, _ = self.make_card()
        self.login(self.amelia)
        resp = self.client.post(
            reverse('chat:swap_action', args=[self.conv.pk, proposal.pk, 'hack']),
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 400)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

    def test_sender_cannot_decline_own_pending_request(self):
        proposal, _ = self.make_card()
        self.login(self.burhania)  # pengirim, bukan penerima
        resp = self.client.post(
            reverse('chat:swap_action', args=[self.conv.pk, proposal.pk, 'decline']),
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 404)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

    def test_swap_flash_message_does_not_leak_to_next_page(self):
        proposal, _ = self.make_card()
        self.login(self.amelia)
        self.client.post(
            reverse('chat:swap_action', args=[self.conv.pk, proposal.pk, 'decline']),
            HTTP_HX_REQUEST='true',
        )
        resp = self.client.get(reverse('chat:index'))
        self.assertEqual([str(m) for m in resp.context['messages']], [])        