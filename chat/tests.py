from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import resolve_url
from django.test import TestCase
from django.urls import reverse

from .models import Conversation, Message

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