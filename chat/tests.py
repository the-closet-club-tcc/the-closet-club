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

from .models import Conversation, Message, Attachment
from . import osm

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