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


class SwapRequestDecisionTests(SwapTestBase):
    def setUp(self):
        self.item = self.items[Clothing.Status.BARTER]
        self.proposal = SwapRequest.objects.create(
            sender=self.viewer, recipient=self.owner,
            offered_item=self.own_item, requested_item=self.item,
        )

    def action_url(self, action):
        return reverse('swap:update_request_status', args=[self.proposal.pk, action])

    def test_recipient_can_accept_without_marking_items_swapped(self):
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(self.action_url('accept')), reverse('swap:requests_incoming'))
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)
        self.assertIsNotNone(self.proposal.status_changed_at)
        for item in (self.item, self.own_item):
            item.refresh_from_db()
            self.assertEqual(item.status, Clothing.Status.BARTER)
        for user, page in ((self.owner, 'swap:requests_incoming'), (self.viewer, 'swap:requests_outgoing')):
            self.client.force_login(user)
            response = self.client.get(reverse(page))
            self.assertContains(response, 'Accepted')
            self.assertNotContains(response, self.action_url('accept'))
            self.assertContains(response, 'Request cancellation')

    def test_recipient_can_decline_and_sender_can_cancel(self):
        for user, action, status, destination in (
            (self.owner, 'decline', SwapRequest.Status.DECLINED, 'swap:requests_incoming'),
            (self.viewer, 'cancel', SwapRequest.Status.CANCELLED, 'swap:requests_outgoing'),
        ):
            with self.subTest(action=action):
                SwapRequest.objects.filter(pk=self.proposal.pk).update(status=SwapRequest.Status.PENDING)
                self.client.force_login(user)
                self.assertRedirects(self.client.post(self.action_url(action)), reverse(destination))
                self.proposal.refresh_from_db()
                self.assertEqual(self.proposal.status, status)
                self.assertIsNotNone(self.proposal.status_changed_at)
                self.assertContains(self.client.get(reverse(destination)), self.proposal.get_status_display())

    def test_wrong_participant_or_outsider_cannot_change_status(self):
        outsider = get_user_model().objects.create_user(username='decision_outsider')
        for user, actions in (
            (self.viewer, ('accept', 'decline')),
            (self.owner, ('cancel',)),
            (outsider, ('accept', 'decline', 'cancel')),
        ):
            self.client.force_login(user)
            for action in actions:
                self.assertEqual(self.client.post(self.action_url(action)).status_code, 404)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SwapRequest.Status.PENDING)
        self.assertIsNone(self.proposal.status_changed_at)

    def test_decision_requires_login_post_and_csrf(self):
        self.assertEqual(self.client.post(self.action_url('accept')).status_code, 302)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        self.assertEqual(browser.get(self.action_url('accept')).status_code, 405)
        self.assertEqual(browser.post(self.action_url('accept')).status_code, 403)
        browser.get(reverse('swap:requests_incoming'))
        self.assertEqual(browser.post(self.action_url('accept'), {
            'csrfmiddlewaretoken': browser.cookies['csrftoken'].value,
        }).status_code, 302)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)

    def test_unknown_action_does_not_change_status(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.action_url('unknown')).status_code, 400)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SwapRequest.Status.PENDING)

    def test_final_decision_cannot_be_overwritten_by_stale_buttons(self):
        for first_action, user in (('decline', self.owner), ('cancel', self.viewer)):
            SwapRequest.objects.filter(pk=self.proposal.pk).update(status=SwapRequest.Status.PENDING)
            self.client.force_login(user)
            self.client.post(self.action_url(first_action))
            self.proposal.refresh_from_db()
            original = (self.proposal.status, self.proposal.status_changed_at)
            for action, actor in (('accept', self.owner), ('decline', self.owner), ('cancel', self.viewer)):
                self.client.force_login(actor)
                self.client.post(self.action_url(action))
                self.proposal.refresh_from_db()
                self.assertEqual((self.proposal.status, self.proposal.status_changed_at), original)

    def test_unavailable_or_changed_owner_items_cannot_be_accepted(self):
        self.client.force_login(self.owner)
        for item in (self.item, self.own_item):
            for status in (Clothing.Status.PERSONAL, Clothing.Status.DONATE, Clothing.Status.SWAPPED):
                Clothing.objects.filter(pk=item.pk).update(status=status)
                self.client.post(self.action_url('accept'))
                self.proposal.refresh_from_db()
                self.assertEqual(self.proposal.status, SwapRequest.Status.PENDING)
            Clothing.objects.filter(pk=item.pk).update(status=Clothing.Status.BARTER)
        Clothing.objects.filter(pk=self.own_item.pk).update(owner=self.owner)
        self.client.post(self.action_url('accept'))
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SwapRequest.Status.PENDING)

    def test_deleted_item_can_be_declined_but_not_accepted(self):
        Clothing.objects.filter(pk=self.own_item.pk).update(photo='')
        self.own_item.delete()
        self.client.force_login(self.owner)
        self.client.post(self.action_url('accept'))
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SwapRequest.Status.PENDING)
        self.client.post(self.action_url('decline'))
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SwapRequest.Status.DECLINED)

    def test_overlapping_items_in_either_position_cannot_be_accepted_twice(self):
        self.client.force_login(self.owner)
        self.client.post(self.action_url('accept'))
        other = get_user_model().objects.create_user(username='another_sender')
        other_item = Clothing.objects.create(owner=other, name='Another piece', status=Clothing.Status.BARTER)
        for offered, requested, sender, recipient in (
            (other_item, self.item, other, self.owner),
            (self.own_item, other_item, self.viewer, other),
            (self.item, other_item, self.owner, other),
            (other_item, self.own_item, other, self.viewer),
        ):
            proposal = SwapRequest.objects.create(
                sender=sender, recipient=recipient, offered_item=offered, requested_item=requested,
            )
            self.client.force_login(recipient)
            self.client.post(reverse('swap:update_request_status', args=[proposal.pk, 'accept']))
            proposal.refresh_from_db()
            self.assertEqual(proposal.status, SwapRequest.Status.PENDING)
        self.assertEqual(SwapRequest.objects.filter(status=SwapRequest.Status.ACCEPTED).count(), 1)

    def test_declined_or_cancelled_request_allows_new_offer(self):
        interest = Interest.objects.create(user=self.viewer, item=self.item)
        for status in (SwapRequest.Status.DECLINED, SwapRequest.Status.CANCELLED):
            SwapRequest.objects.filter(sender=self.viewer, requested_item=self.item).update(status=status)
            self.client.force_login(self.viewer)
            self.client.post(reverse('swap:propose', args=[interest.pk]), {'offered_item': self.own_item.pk})
            self.assertEqual(SwapRequest.objects.filter(status=SwapRequest.Status.PENDING).count(), 1)

    def test_accepted_request_continues_chat_instead_of_creating_duplicate_offer(self):
        interest = Interest.objects.create(user=self.viewer, item=self.item)
        self.client.force_login(self.owner)
        self.client.post(self.action_url('accept'))
        self.client.force_login(self.viewer)
        response = self.client.post(reverse('swap:propose', args=[interest.pk]), {'offered_item': self.own_item.pk})
        self.assertRedirects(response, reverse('chat:room', args=[Conversation.objects.get().pk]))
        self.assertEqual(SwapRequest.objects.count(), 1)
        self.assertContains(self.client.get(reverse('swap:interested')), 'Continue to chat')

    def test_buttons_match_participant_role(self):
        self.client.force_login(self.owner)
        incoming = self.client.get(reverse('swap:requests_incoming'))
        self.assertContains(incoming, self.action_url('accept'))
        self.assertContains(incoming, self.action_url('decline'))
        self.assertNotContains(incoming, self.action_url('cancel'))
        self.client.force_login(self.viewer)
        outgoing = self.client.get(reverse('swap:requests_outgoing'))
        self.assertContains(outgoing, self.action_url('cancel'))
        self.assertNotContains(outgoing, self.action_url('accept'))
        self.assertNotContains(outgoing, self.action_url('decline'))


class SwapLifecycleTests(SwapTestBase):
    def setUp(self):
        self.item = self.items[Clothing.Status.BARTER]
        self.proposal = SwapRequest.objects.create(
            sender=self.viewer, recipient=self.owner,
            offered_item=self.own_item, requested_item=self.item,
            status=SwapRequest.Status.ACCEPTED,
        )
        self.outsider = get_user_model().objects.create_user(username='lifecycle_outsider')
        self.third_item = Clothing.objects.create(
            owner=self.outsider, name='Third piece', status=Clothing.Status.TOP_UP,
        )

    def action_url(self, action):
        return reverse('swap:update_request_status', args=[self.proposal.pk, action])

    def act(self, user, action):
        self.client.force_login(user)
        response = self.client.post(self.action_url(action))
        self.proposal.refresh_from_db()
        return response

    def test_both_people_must_confirm_in_either_order(self):
        for first, second in ((self.viewer, self.owner), (self.owner, self.viewer)):
            with self.subTest(first=first.username):
                SwapRequest.objects.filter(pk=self.proposal.pk).update(
                    status=SwapRequest.Status.ACCEPTED, sender_confirmed_at=None, recipient_confirmed_at=None,
                )
                Clothing.objects.filter(pk__in=[self.item.pk, self.own_item.pk]).update(status=Clothing.Status.BARTER)
                self.act(first, 'complete')
                self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)
                self.assertEqual(bool(self.proposal.sender_confirmed_at), first == self.viewer)
                self.assertEqual(bool(self.proposal.recipient_confirmed_at), first == self.owner)
                self.item.refresh_from_db()
                self.own_item.refresh_from_db()
                self.assertEqual(self.item.status, Clothing.Status.BARTER)
                self.assertEqual(self.own_item.status, Clothing.Status.BARTER)
                self.act(second, 'complete')
                self.assertEqual(self.proposal.status, SwapRequest.Status.COMPLETED)
                self.assertIsNotNone(self.proposal.sender_confirmed_at)
                self.assertIsNotNone(self.proposal.recipient_confirmed_at)
                self.item.refresh_from_db()
                self.own_item.refresh_from_db()
                self.assertEqual(self.item.status, Clothing.Status.SWAPPED)
                self.assertEqual(self.own_item.status, Clothing.Status.SWAPPED)
                self.assertEqual(self.item.owner_id, self.owner.pk)
                self.assertEqual(self.own_item.owner_id, self.viewer.pk)

    def test_repeat_confirmation_cannot_confirm_for_other_person(self):
        self.act(self.viewer, 'complete')
        first_time = self.proposal.sender_confirmed_at
        self.client.post(self.action_url('complete'), {'recipient_confirmed_at': '2026-10-27', 'status': 'completed'})
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.sender_confirmed_at, first_time)
        self.assertIsNone(self.proposal.recipient_confirmed_at)
        self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)

    def test_completion_is_terminal_and_history_still_shows_pieces(self):
        self.act(self.viewer, 'complete')
        self.act(self.owner, 'complete')
        completion_time = self.proposal.status_changed_at
        for user in (self.viewer, self.owner):
            for action in ('complete', 'cancel', 'keep'):
                self.act(user, action)
                self.assertEqual(self.proposal.status, SwapRequest.Status.COMPLETED)
                self.assertEqual(self.proposal.status_changed_at, completion_time)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('swap:requests_outgoing'))
        self.assertContains(response, 'Completed')
        self.assertContains(response, self.item.name)
        self.assertContains(response, self.own_item.name)
        self.assertNotContains(response, 'Confirm completed')
        self.assertNotContains(response, 'Request cancellation')

    def test_accepted_items_are_excluded_from_discovery_in_all_filters(self):
        self.client.force_login(self.outsider)
        for status in ('', 'barter', 'top_up'):
            response = self.client.get(reverse('swap:index'), {'status': status})
            self.assertNotIn(self.item, response.context['items'])
            self.assertNotIn(self.own_item, response.context['items'])
        for item in (self.item, self.own_item):
            response = self.client.post(reverse('swap:save_interest', args=[item.pk]))
            self.assertEqual(response.status_code, 404)

    def test_reserved_target_cannot_receive_new_offer_and_is_labelled_in_saved_list(self):
        interest = Interest.objects.create(user=self.outsider, item=self.item)
        self.client.force_login(self.outsider)
        url = reverse('swap:propose', args=[interest.pk])
        response = self.client.get(reverse('swap:interested'))
        self.assertContains(response, 'currently reserved')
        self.assertNotContains(response, f'href="{url}"')
        self.assertEqual(self.client.post(url, {'offered_item': self.third_item.pk}).status_code, 400)
        self.assertEqual(SwapRequest.objects.count(), 1)

    def test_reserved_own_item_is_excluded_from_form_and_rejected_on_post(self):
        interest = Interest.objects.create(user=self.viewer, item=self.third_item)
        self.client.force_login(self.viewer)
        url = reverse('swap:propose', args=[interest.pk])
        response = self.client.get(url)
        self.assertNotIn(self.own_item, response.context['form'].fields['offered_item'].queryset)
        self.assertEqual(self.client.post(url, {'offered_item': self.own_item.pk}).status_code, 400)
        self.assertEqual(SwapRequest.objects.count(), 1)

    def test_cancellation_needs_both_people_and_releases_pieces(self):
        for first, second in ((self.viewer, self.owner), (self.owner, self.viewer)):
            with self.subTest(first=first.username):
                SwapRequest.objects.filter(pk=self.proposal.pk).update(
                    status=SwapRequest.Status.ACCEPTED,
                    cancellation_requested_by=None, cancellation_requested_at=None,
                )
                self.act(first, 'cancel')
                self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)
                self.assertEqual(self.proposal.cancellation_requested_by_id, first.pk)
                self.act(first, 'cancel')
                self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)
                self.client.force_login(self.outsider)
                self.assertNotIn(self.item, self.client.get(reverse('swap:index')).context['items'])
                self.act(second, 'cancel')
                self.assertEqual(self.proposal.status, SwapRequest.Status.CANCELLED)
                self.client.force_login(self.outsider)
                items = self.client.get(reverse('swap:index')).context['items']
                self.assertIn(self.item, items)
                self.assertIn(self.own_item, items)
                self.item.refresh_from_db()
                self.assertEqual(self.item.status, Clothing.Status.BARTER)

    def test_requested_cancellation_blocks_completion_until_dismissed(self):
        self.act(self.viewer, 'complete')
        self.act(self.owner, 'cancel')
        self.act(self.owner, 'complete')
        self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)
        self.assertIsNone(self.proposal.recipient_confirmed_at)
        self.act(self.viewer, 'keep')
        self.assertIsNone(self.proposal.cancellation_requested_by_id)
        self.assertIsNone(self.proposal.cancellation_requested_at)
        self.act(self.owner, 'complete')
        self.assertEqual(self.proposal.status, SwapRequest.Status.COMPLETED)

    def test_cancellation_can_be_withdrawn_by_requester(self):
        self.act(self.owner, 'cancel')
        self.act(self.owner, 'keep')
        self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)
        self.assertIsNone(self.proposal.cancellation_requested_by_id)

    def test_cancellation_after_one_confirmation_does_not_mark_items_swapped(self):
        self.act(self.viewer, 'complete')
        self.act(self.viewer, 'cancel')
        self.act(self.owner, 'cancel')
        self.act(self.owner, 'complete')
        self.assertEqual(self.proposal.status, SwapRequest.Status.CANCELLED)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Clothing.Status.BARTER)

    def test_unavailable_items_block_completion_but_can_still_cancel(self):
        self.act(self.viewer, 'complete')
        Clothing.objects.filter(pk=self.item.pk).update(status=Clothing.Status.PERSONAL)
        self.act(self.owner, 'complete')
        self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)
        self.assertIsNone(self.proposal.recipient_confirmed_at)
        self.act(self.viewer, 'cancel')
        self.act(self.owner, 'cancel')
        self.assertEqual(self.proposal.status, SwapRequest.Status.CANCELLED)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Clothing.Status.PERSONAL)

    def test_deleted_item_blocks_completion_without_partial_update(self):
        self.act(self.viewer, 'complete')
        Clothing.objects.filter(pk=self.item.pk).update(photo='')
        self.item.delete()
        self.act(self.owner, 'complete')
        self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)
        self.assertIsNone(self.proposal.recipient_confirmed_at)
        self.own_item.refresh_from_db()
        self.assertEqual(self.own_item.status, Clothing.Status.BARTER)

    def test_ownership_change_blocks_completion(self):
        self.act(self.viewer, 'complete')
        Clothing.objects.filter(pk=self.own_item.pk).update(owner=self.outsider)
        self.act(self.owner, 'complete')
        self.assertEqual(self.proposal.status, SwapRequest.Status.ACCEPTED)
        self.assertIsNone(self.proposal.recipient_confirmed_at)

    def test_other_pending_offers_for_completed_pieces_are_closed(self):
        overlap = SwapRequest.objects.create(
            sender=self.outsider, recipient=self.owner,
            offered_item=self.third_item, requested_item=self.item,
        )
        unrelated = SwapRequest.objects.create(
            sender=self.outsider, recipient=self.owner,
            offered_item=self.third_item, requested_item=self.items[Clothing.Status.TOP_UP],
        )
        self.act(self.viewer, 'complete')
        self.act(self.owner, 'complete')
        overlap.refresh_from_db()
        unrelated.refresh_from_db()
        self.assertEqual(overlap.status, SwapRequest.Status.CANCELLED)
        self.assertEqual(unrelated.status, SwapRequest.Status.PENDING)
        self.third_item.refresh_from_db()
        self.assertEqual(self.third_item.status, Clothing.Status.TOP_UP)

    def test_only_participants_can_confirm_cancel_or_keep(self):
        for action in ('complete', 'cancel', 'keep'):
            self.assertEqual(self.act(self.outsider, action).status_code, 404)
        self.assertIsNone(self.proposal.sender_confirmed_at)
        self.assertIsNone(self.proposal.recipient_confirmed_at)
        self.assertIsNone(self.proposal.cancellation_requested_by_id)

    def test_new_actions_require_post_and_csrf(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.viewer)
        for action in ('complete', 'cancel', 'keep'):
            self.assertEqual(browser.get(self.action_url(action)).status_code, 405)
            self.assertEqual(browser.post(self.action_url(action)).status_code, 403)
        browser.get(reverse('swap:requests_outgoing'))
        self.assertEqual(browser.post(self.action_url('complete'), {
            'csrfmiddlewaretoken': browser.cookies['csrftoken'].value,
        }).status_code, 302)
        self.proposal.refresh_from_db()
        self.assertIsNotNone(self.proposal.sender_confirmed_at)

    def test_pending_request_cannot_be_completed(self):
        SwapRequest.objects.filter(pk=self.proposal.pk).update(status=SwapRequest.Status.PENDING)
        self.act(self.viewer, 'complete')
        self.act(self.owner, 'complete')
        self.assertEqual(self.proposal.status, SwapRequest.Status.PENDING)
        self.assertIsNone(self.proposal.sender_confirmed_at)
        self.assertIsNone(self.proposal.recipient_confirmed_at)

    def test_confirmation_and_cancellation_controls_reflect_each_person(self):
        self.act(self.viewer, 'complete')
        response = self.client.get(reverse('swap:requests_outgoing'))
        self.assertNotContains(response, 'Confirm completed')
        self.assertContains(response, f'{self.viewer.username}: confirmed')
        self.act(self.viewer, 'cancel')
        response = self.client.get(reverse('swap:requests_outgoing'))
        self.assertContains(response, 'Withdraw cancellation')
        self.assertNotContains(response, 'Agree to cancel')
        self.client.force_login(self.owner)
        response = self.client.get(reverse('swap:requests_incoming'))
        self.assertContains(response, 'Agree to cancel')
        self.assertContains(response, 'Keep swap')
        self.assertNotContains(response, 'Confirm completed')


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
