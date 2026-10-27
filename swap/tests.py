from urllib.parse import parse_qs, urlsplit
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from closet.models import Clothing
from chat.models import Conversation, Message

from .models import Interest, SwapRequest


class SwapTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = get_user_model().objects.create_user(username='swap_viewer')
        cls.owner = get_user_model().objects.create_user(username='swap_owner')
        cls.items = {}
        for status in Clothing.Status.values:
            cls.items[status] = Clothing.objects.create(
                owner=cls.owner, name=f'Item {status}', status=status,
                photo=f'clothes/{status}.jpg', size=Clothing.Size.ONE,
                condition=Clothing.Condition.VERY_GOOD,
                description='Soft cotton with a relaxed fit.',
            )
        cls.own_item = Clothing.objects.create(
            owner=cls.viewer, name='My own shirt', status=Clothing.Status.BARTER,
            photo='clothes/own.jpg',
        )


class SwapPageTests(SwapTestBase):
    def test_only_swap_offers_from_other_owners_are_shown(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('swap:index'))
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(response.context['items'], [
            self.items[Clothing.Status.BARTER], self.items[Clothing.Status.TOP_UP],
        ])
        for status in (Clothing.Status.PERSONAL, Clothing.Status.DONATE, Clothing.Status.SWAPPED):
            self.assertNotContains(response, f'Item {status}')
        self.assertNotContains(response, 'My own shirt')

    def test_guest_is_redirected_to_login_for_all_filters(self):
        for query in ('', '?status=barter', '?status=top_up'):
            with self.subTest(query=query):
                url = reverse('swap:index') + query
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                redirect_url = urlsplit(response['Location'])
                self.assertEqual(redirect_url.path, reverse('login'))
                self.assertEqual(parse_qs(redirect_url.query)['next'], [url])

    def test_each_offer_filter(self):
        self.client.force_login(self.viewer)
        for status in (Clothing.Status.BARTER, Clothing.Status.TOP_UP):
            with self.subTest(status=status):
                response = self.client.get(reverse('swap:index'), {'status': status})
                self.assertEqual(list(response.context['items']), [self.items[status]])
                self.assertEqual(response.context['current_status'], status)
                self.assertContains(response, 'Explore all swap options')

    def test_unsupported_filters_do_not_expose_other_statuses(self):
        self.client.force_login(self.viewer)
        for status in ('personal', 'donate', 'swapped', 'invalid'):
            with self.subTest(status=status):
                response = self.client.get(reverse('swap:index'), {'status': status})
                self.assertEqual(response.context['current_status'], '')
                self.assertCountEqual(response.context['items'], [
                    self.items[Clothing.Status.BARTER], self.items[Clothing.Status.TOP_UP],
                ])

    def test_card_uses_uploaded_photo_and_display_labels(self):
        self.client.force_login(self.viewer)
        item = self.items[Clothing.Status.TOP_UP]
        response = self.client.get(reverse('swap:index'), {'status': 'top_up'})
        self.assertContains(response, f'src="{item.photo.url}"')
        self.assertContains(response, 'Size One Size &middot; Very Good')
        self.assertContains(response, 'data-offer="Swap + top-up"')
        self.assertContains(response, 'data-owner="swap_owner"')
        self.assertContains(response, 'data-description="Soft cotton with a relaxed fit."')
        self.assertNotContains(response, 'swap-shirt.png')

    def test_empty_filter_and_empty_catalog_have_relevant_messages(self):
        self.client.force_login(self.viewer)
        Clothing.objects.filter(status=Clothing.Status.TOP_UP).update(status=Clothing.Status.PERSONAL)
        response = self.client.get(reverse('swap:index'), {'status': 'top_up'})
        self.assertContains(response, 'No matching items')
        self.assertContains(response, 'Try all swap options')
        self.assertContains(response, '<div class="swap-finished" id="swap-finished" >', html=False)

        Clothing.objects.all().update(status=Clothing.Status.PERSONAL)
        response = self.client.get(reverse('swap:index'))
        self.assertContains(response, 'No swap items yet')
        self.assertNotContains(response, '<article class="swap-card"')

    def test_missing_photo_has_a_placeholder(self):
        self.client.force_login(self.viewer)
        Clothing.objects.filter(pk=self.items[Clothing.Status.TOP_UP].pk).update(photo='')
        response = self.client.get(reverse('swap:index'), {'status': 'top_up'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No photo available')


class InterestTests(SwapTestBase):
    def setUp(self):
        self.client.force_login(self.viewer)
        self.item = self.items[Clothing.Status.BARTER]
        self.save_url = reverse('swap:save_interest', args=[self.item.pk])

    def test_save_is_persistent_and_excluded_from_every_discovery_filter(self):
        response = self.client.post(self.save_url)
        self.assertJSONEqual(response.content, {'saved': True})
        self.assertTrue(Interest.objects.filter(user=self.viewer, item=self.item).exists())
        second_browser = Client()
        second_browser.force_login(self.viewer)
        response = second_browser.get(reverse('swap:interested'))
        self.assertContains(response, self.item.name)
        self.assertContains(response, f'src="{self.item.photo.url}"')
        self.assertContains(response, 'View Details')
        self.assertContains(response, 'Remove')
        for status in ('', 'barter', 'top_up'):
            response = second_browser.get(reverse('swap:index'), {'status': status})
            self.assertNotIn(self.item, response.context['items'])
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Clothing.Status.BARTER)

    def test_repeated_save_creates_only_one_interest(self):
        self.client.post(self.save_url)
        self.client.post(self.save_url)
        self.assertEqual(Interest.objects.filter(user=self.viewer, item=self.item).count(), 1)

    def test_top_up_item_can_be_saved(self):
        item = self.items[Clothing.Status.TOP_UP]
        response = self.client.post(reverse('swap:save_interest', args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Interest.objects.filter(user=self.viewer, item=item).exists())

    def test_login_required_to_save_or_view_interests(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.save_url).status_code, 401)
        self.assertEqual(self.client.get(reverse('swap:interested')).status_code, 302)
        self.assertFalse(Interest.objects.exists())

    def test_only_available_items_from_other_users_can_be_saved(self):
        blocked = [self.own_item] + [
            self.items[status] for status in (
                Clothing.Status.PERSONAL, Clothing.Status.DONATE, Clothing.Status.SWAPPED,
            )
        ]
        for item in blocked:
            with self.subTest(item=item.name):
                response = self.client.post(reverse('swap:save_interest', args=[item.pk]))
                self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.post(reverse('swap:save_interest', args=[999999])).status_code, 404)
        self.assertFalse(Interest.objects.exists())

    def test_guest_cannot_remove_an_interest(self):
        interest = Interest.objects.create(user=self.viewer, item=self.item)
        self.client.logout()
        response = self.client.post(reverse('swap:remove_interest', args=[interest.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response['Location']).path, reverse('login'))
        self.assertTrue(Interest.objects.filter(pk=interest.pk).exists())

    def test_list_and_removal_are_scoped_to_current_user(self):
        own_interest = Interest.objects.create(user=self.viewer, item=self.item)
        other_interest = Interest.objects.create(user=self.owner, item=self.own_item)
        response = self.client.get(reverse('swap:interested'))
        self.assertEqual(list(response.context['interests']), [own_interest])
        response = self.client.post(reverse('swap:remove_interest', args=[other_interest.pk]))
        self.assertRedirects(response, reverse('swap:interested'))
        self.assertTrue(Interest.objects.filter(pk=other_interest.pk).exists())

    def test_remove_restores_item_to_discovery(self):
        interest = Interest.objects.create(user=self.viewer, item=self.item)
        response = self.client.post(reverse('swap:remove_interest', args=[interest.pk]))
        self.assertRedirects(response, reverse('swap:interested'))
        self.assertFalse(Interest.objects.filter(pk=interest.pk).exists())
        self.assertContains(self.client.get(reverse('swap:interested')), 'No saved pieces yet')
        response = self.client.get(reverse('swap:index'), {'status': 'barter'})
        self.assertIn(self.item, response.context['items'])

    def test_unavailable_items_do_not_leak_details(self):
        Interest.objects.create(user=self.viewer, item=self.item)
        for status in (Clothing.Status.PERSONAL, Clothing.Status.DONATE, Clothing.Status.SWAPPED):
            with self.subTest(status=status):
                Clothing.objects.filter(pk=self.item.pk).update(status=status)
                response = self.client.get(reverse('swap:interested'))
                self.assertContains(response, 'Item no longer available')
                self.assertContains(response, 'Remove')
                self.assertNotContains(response, self.item.name)
                self.assertNotContains(response, self.item.photo.url)
                self.assertNotContains(response, self.item.description)
                self.assertNotContains(response, 'data-owner="swap_owner"')

    def test_state_changes_require_post_and_csrf(self):
        interest = Interest.objects.create(user=self.viewer, item=self.item)
        remove_url = reverse('swap:remove_interest', args=[interest.pk])
        self.assertEqual(self.client.get(self.save_url).status_code, 405)
        self.assertEqual(self.client.get(remove_url).status_code, 405)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.viewer)
        self.assertEqual(browser.post(self.save_url).status_code, 403)
        self.assertEqual(browser.post(remove_url).status_code, 403)
        browser.get(reverse('swap:index'))
        token = browser.cookies['csrftoken'].value
        self.assertEqual(browser.post(self.save_url, HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(browser.post(remove_url, HTTP_X_CSRFTOKEN=token).status_code, 302)

    def test_empty_list_has_a_link_back_to_discovery(self):
        response = self.client.get(reverse('swap:interested'))
        self.assertContains(response, 'No saved pieces yet')
        self.assertContains(response, f'href="{reverse("swap:index")}"')


class SwapRequestTests(SwapTestBase):
    def setUp(self):
        self.client.force_login(self.viewer)
        self.item = self.items[Clothing.Status.BARTER]
        self.interest = Interest.objects.create(user=self.viewer, item=self.item)
        self.propose_url = reverse('swap:propose', args=[self.interest.pk])
        self.incoming_url = reverse('swap:requests_incoming')
        self.outgoing_url = reverse('swap:requests_outgoing')

    def send_request(self):
        return self.client.post(self.propose_url, {'offered_item': self.own_item.pk})

    def test_proposal_form_only_lists_own_available_items(self):
        eligible = [self.own_item]
        for status in Clothing.Status.values:
            item = Clothing.objects.create(owner=self.viewer, name=f'My {status}', status=status)
            if status in (Clothing.Status.BARTER, Clothing.Status.TOP_UP):
                eligible.append(item)
        response = self.client.get(self.propose_url)
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(response.context['form'].fields['offered_item'].queryset, eligible)
        self.assertContains(response, self.item.name)
        self.assertFalse(SwapRequest.objects.exists())

    def test_request_is_persistent_and_shown_to_both_participants(self):
        response = self.send_request()
        conversation = Conversation.objects.get()
        self.assertRedirects(response, reverse('chat:room', args=[conversation.pk]))
        self.assertEqual({conversation.user1_id, conversation.user2_id}, {self.viewer.pk, self.owner.pk})
        self.assertEqual(conversation.item_id, self.item.pk)
        self.assertEqual(conversation.item_name, self.item.name)
        self.assertFalse(Message.objects.exists())
        proposal = SwapRequest.objects.get()
        self.assertEqual(proposal.sender, self.viewer)
        self.assertEqual(proposal.recipient, self.owner)
        self.assertEqual(proposal.offered_item, self.own_item)
        self.assertEqual(proposal.requested_item, self.item)
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)
        browser = Client()
        for user, url in ((self.viewer, self.outgoing_url), (self.owner, self.incoming_url)):
            with self.subTest(user=user.username):
                browser.force_login(user)
                response = browser.get(url)
                self.assertEqual(list(response.context['swap_requests']), [proposal])
                self.assertContains(response, self.item.name)
                self.assertContains(response, self.own_item.name)
                self.assertContains(response, 'Pending')
        self.item.refresh_from_db()
        self.own_item.refresh_from_db()
        self.assertEqual(self.item.status, Clothing.Status.BARTER)
        self.assertEqual(self.own_item.status, Clothing.Status.BARTER)

    def test_repeated_submission_keeps_original_offer(self):
        self.send_request()
        alternative = Clothing.objects.create(owner=self.viewer, name='Another offer', status=Clothing.Status.BARTER)
        response = self.client.post(self.propose_url, {'offered_item': alternative.pk})
        self.assertRedirects(response, reverse('chat:room', args=[Conversation.objects.get().pk]))
        self.assertEqual(SwapRequest.objects.count(), 1)
        self.assertEqual(SwapRequest.objects.get().offered_item, self.own_item)
        response = self.client.get(reverse('swap:interested'))
        self.assertContains(response, 'Continue to chat')
        self.assertNotContains(response, f'href="{self.propose_url}"')

    def test_offered_item_cannot_be_forged_or_unavailable(self):
        for value in (self.item.pk, 999999, 'invalid', ''):
            with self.subTest(value=value):
                response = self.client.post(self.propose_url, {'offered_item': value})
                self.assertEqual(response.status_code, 400)
        for status in (Clothing.Status.PERSONAL, Clothing.Status.DONATE, Clothing.Status.SWAPPED):
            with self.subTest(status=status):
                Clothing.objects.filter(pk=self.own_item.pk).update(status=status)
                self.assertEqual(self.send_request().status_code, 400)
        self.assertFalse(SwapRequest.objects.exists())
        self.assertFalse(Conversation.objects.exists())

    def test_unavailable_target_does_not_accept_requests_or_expose_details(self):
        for status in (Clothing.Status.PERSONAL, Clothing.Status.DONATE, Clothing.Status.SWAPPED):
            with self.subTest(status=status):
                Clothing.objects.filter(pk=self.item.pk).update(status=status)
                response = self.send_request()
                self.assertEqual(response.status_code, 400)
                self.assertNotContains(response, self.item.name, status_code=400)
                self.assertNotContains(response, self.item.photo.url, status_code=400)
        self.assertFalse(SwapRequest.objects.exists())

    def test_self_swap_and_other_users_interests_are_rejected(self):
        self_interest = Interest.objects.create(user=self.viewer, item=self.own_item)
        response = self.client.post(reverse('swap:propose', args=[self_interest.pk]), {'offered_item': self.own_item.pk})
        self.assertEqual(response.status_code, 400)
        other_interest = Interest.objects.create(user=self.owner, item=self.own_item)
        other_url = reverse('swap:propose', args=[other_interest.pk])
        self.assertEqual(self.client.get(other_url).status_code, 404)
        self.assertEqual(self.client.post(other_url, {'offered_item': self.own_item.pk}).status_code, 404)
        self.assertFalse(SwapRequest.objects.exists())

    def test_client_cannot_choose_sender_recipient_or_status(self):
        self.client.post(self.propose_url, {
            'offered_item': self.own_item.pk, 'sender': self.owner.pk,
            'recipient': self.viewer.pk, 'status': 'accepted',
        })
        proposal = SwapRequest.objects.get()
        self.assertEqual(proposal.sender, self.viewer)
        self.assertEqual(proposal.recipient, self.owner)
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

    def test_request_lists_are_private_and_separated_by_direction(self):
        self.send_request()
        self.assertFalse(self.client.get(self.incoming_url).context['swap_requests'])
        self.client.force_login(self.owner)
        self.assertFalse(self.client.get(self.outgoing_url).context['swap_requests'])
        outsider = get_user_model().objects.create_user(username='swap_outsider')
        self.client.force_login(outsider)
        for url in (self.incoming_url, self.outgoing_url):
            response = self.client.get(url)
            self.assertFalse(response.context['swap_requests'])
            self.assertNotContains(response, self.item.name)

    def test_login_and_csrf_are_required(self):
        self.client.logout()
        for url in (self.propose_url, self.incoming_url, self.outgoing_url):
            self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.send_request().status_code, 302)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.viewer)
        self.assertEqual(browser.post(self.propose_url, {'offered_item': self.own_item.pk}).status_code, 403)
        self.assertFalse(SwapRequest.objects.exists())
        browser.get(self.propose_url)
        response = browser.post(self.propose_url, {
            'offered_item': self.own_item.pk,
            'csrfmiddlewaretoken': browser.cookies['csrftoken'].value,
        })
        self.assertRedirects(response, reverse('chat:room', args=[Conversation.objects.get().pk]))
        self.assertEqual(browser.put(
            self.propose_url, HTTP_X_CSRFTOKEN=browser.cookies['csrftoken'].value,
        ).status_code, 405)

    def test_empty_closet_has_a_useful_next_step(self):
        Clothing.objects.filter(pk=self.own_item.pk).update(status=Clothing.Status.PERSONAL)
        response = self.client.get(self.propose_url)
        self.assertContains(response, 'Go to My Closet')
        self.assertNotContains(response, 'Continue to chat')

    def test_top_up_items_can_be_proposed_without_changing_status(self):
        top_up = self.items[Clothing.Status.TOP_UP]
        interest = Interest.objects.create(user=self.viewer, item=top_up)
        Clothing.objects.filter(pk=self.own_item.pk).update(status=Clothing.Status.TOP_UP)
        response = self.client.post(reverse('swap:propose', args=[interest.pk]), {'offered_item': self.own_item.pk})
        self.assertRedirects(response, reverse('chat:room', args=[Conversation.objects.get().pk]))
        self.assertEqual(SwapRequest.objects.get().requested_item, top_up)

    def test_changed_availability_hides_item_details_in_both_lists(self):
        self.send_request()
        Clothing.objects.filter(pk__in=[self.item.pk, self.own_item.pk]).update(status=Clothing.Status.PERSONAL)
        for user, url in ((self.viewer, self.outgoing_url), (self.owner, self.incoming_url)):
            self.client.force_login(user)
            response = self.client.get(url)
            self.assertContains(response, 'Item no longer available', count=2)
            for item in (self.item, self.own_item):
                self.assertNotContains(response, item.name)
                self.assertNotContains(response, item.photo.url)

    def test_removing_interest_or_deleting_item_preserves_request_record(self):
        self.send_request()
        self.interest.delete()
        Clothing.objects.filter(pk=self.item.pk).update(photo='')
        self.item.delete()
        proposal = SwapRequest.objects.get()
        self.assertIsNone(proposal.requested_item)
        response = self.client.get(self.outgoing_url)
        self.assertContains(response, 'Item no longer available')
        self.assertContains(response, self.own_item.name)

    def test_empty_request_lists_offer_a_next_step(self):
        self.assertContains(self.client.get(self.incoming_url), 'No incoming requests yet')
        self.assertContains(self.client.get(self.outgoing_url), 'No outgoing requests yet')

    def test_selecting_offer_reuses_existing_chat_and_preserves_messages(self):
        conversation = Conversation.objects.create(user1=self.owner, user2=self.viewer)
        message = Message.objects.create(conversation=conversation, sender=self.owner, content='Hello!')
        self.assertRedirects(self.send_request(), reverse('chat:room', args=[conversation.pk]))
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(list(conversation.messages.all()), [message])
        self.assertEqual(SwapRequest.objects.get().offered_item, self.own_item)

    def test_saved_offer_can_continue_to_chat_without_choosing_again(self):
        self.send_request()
        conversation = Conversation.objects.get()
        response = self.client.post(self.propose_url)
        self.assertRedirects(response, reverse('chat:room', args=[conversation.pk]))
        self.assertEqual(SwapRequest.objects.count(), 1)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_opening_form_or_submitting_without_an_offer_does_not_start_chat(self):
        response = self.client.get(self.propose_url)
        self.assertContains(response, 'Continue to chat')
        self.assertFalse(Conversation.objects.exists())
        response = self.client.post(self.propose_url)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.context['form'].errors['offered_item'])
        self.assertFalse(Conversation.objects.exists())
        self.assertFalse(SwapRequest.objects.exists())


class SwapChatIntegrationTests(SwapTestBase):
    def setUp(self):
        self.item = self.items[Clothing.Status.BARTER]
        self.proposal = SwapRequest.objects.create(
            sender=self.viewer, recipient=self.owner,
            offered_item=self.own_item, requested_item=self.item,
        )
        self.client.force_login(self.viewer)

    def chat_form(self, page_url, partner):
        action = reverse('chat:start', args=[partner.pk])

        class ChatFormParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_form = False
                self.found = False
                self.fields = {}

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'form':
                    self.in_form = attrs.get('action') == action and attrs.get('method') == 'post'
                    self.found |= self.in_form
                if self.in_form and tag == 'input' and attrs.get('name'):
                    self.fields[attrs['name']] = attrs.get('value', '')

            def handle_endtag(self, tag):
                if tag == 'form':
                    self.in_form = False

        response = self.client.get(page_url)
        self.assertEqual(response.status_code, 200)
        parser = ChatFormParser()
        parser.feed(response.content.decode())
        self.assertTrue(parser.found)
        self.assertIn('csrfmiddlewaretoken', parser.fields)
        return action, parser.fields

    def test_both_request_lists_open_the_same_chat_with_item_context(self):
        for user, partner, page in (
            (self.viewer, self.owner, 'swap:requests_outgoing'),
            (self.owner, self.viewer, 'swap:requests_incoming'),
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                action, fields = self.chat_form(reverse(page), partner)
                self.assertEqual(fields['item_id'], str(self.item.pk))
                self.assertEqual(fields['item_name'], self.item.name)
                response = self.client.post(action, fields)
                conversation = Conversation.objects.get()
                self.assertRedirects(response, reverse('chat:room', args=[conversation.pk]))
                self.assertTrue(conversation.has_participant(self.viewer))
                self.assertTrue(conversation.has_participant(self.owner))
                self.assertEqual(conversation.item_id, self.item.pk)
                self.assertEqual(conversation.item_name, self.item.name)
        self.assertFalse(Message.objects.exists())
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SwapRequest.Status.PENDING)

    def test_existing_conversation_and_messages_are_preserved(self):
        conversation = Conversation.objects.create(user1=self.owner, user2=self.viewer)
        message = Message.objects.create(conversation=conversation, sender=self.owner, content='Hello!')
        action, fields = self.chat_form(reverse('swap:requests_outgoing'), self.owner)
        for _ in range(2):
            self.assertRedirects(self.client.post(action, fields), reverse('chat:room', args=[conversation.pk]))
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(list(conversation.messages.all()), [message])

    def test_participants_can_exchange_messages_and_outsiders_cannot_read_or_send(self):
        action, fields = self.chat_form(reverse('swap:requests_outgoing'), self.owner)
        self.client.post(action, fields)
        conversation = Conversation.objects.get()
        send_url = reverse('chat:send', args=[conversation.pk])
        messages_url = reverse('chat:messages', args=[conversation.pk])
        self.assertEqual(self.client.post(send_url, {'content': 'Is the jacket still available?'}).status_code, 200)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(messages_url), 'Is the jacket still available?')
        self.assertEqual(self.client.post(send_url, {'content': 'Yes, it is.'}).status_code, 200)
        self.client.force_login(self.viewer)
        self.assertContains(self.client.get(messages_url), 'Yes, it is.')
        outsider = get_user_model().objects.create_user(username='chat_outsider')
        self.client.force_login(outsider)
        for url in (messages_url, reverse('chat:room', args=[conversation.pk])):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(send_url, {'content': 'Uninvited'}).status_code, 404)
        self.assertEqual(conversation.messages.count(), 2)
        response = self.client.get(reverse('swap:requests_incoming'))
        self.assertNotContains(response, f'action="{action}"')

    def test_unavailable_or_deleted_item_is_not_sent_as_chat_context(self):
        Clothing.objects.filter(pk=self.item.pk).update(status=Clothing.Status.PERSONAL)
        action, fields = self.chat_form(reverse('swap:requests_outgoing'), self.owner)
        self.assertNotIn('item_id', fields)
        self.assertNotIn('item_name', fields)
        self.client.post(action, fields)
        conversation = Conversation.objects.get()
        self.assertIsNone(conversation.item_id)
        self.assertEqual(conversation.item_name, '')
        Clothing.objects.filter(pk=self.item.pk).update(photo='')
        self.item.delete()
        action, fields = self.chat_form(reverse('swap:requests_outgoing'), self.owner)
        self.assertNotIn('item_name', fields)
        self.assertRedirects(self.client.post(action, fields), reverse('chat:room', args=[conversation.pk]))

    def test_chat_handoff_requires_login_post_and_csrf(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.viewer)
        action, fields = self.chat_form(reverse('swap:requests_outgoing'), self.owner)
        self.assertEqual(self.client.get(action).status_code, 405)
        self.assertEqual(self.client.post(action, {}).status_code, 403)
        self.assertFalse(Conversation.objects.exists())
        self.assertEqual(self.client.post(action, fields).status_code, 302)
        conversation = Conversation.objects.get()
        send_url = reverse('chat:send', args=[conversation.pk])
        self.assertEqual(self.client.post(send_url, {'content': 'Hello'}).status_code, 403)
        self.assertEqual(self.client.post(send_url, {
            'content': 'Hello', 'csrfmiddlewaretoken': fields['csrfmiddlewaretoken'],
        }).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('chat:room', args=[conversation.pk])).status_code, 302)
        self.assertEqual(Client().post(action, fields).status_code, 302)

    def test_swap_navigation_does_not_have_a_separate_messages_shortcut(self):
        response = self.client.get(reverse('swap:index'))
        self.assertNotContains(response, '>Messages</a>')
