from urllib.parse import parse_qs, urlsplit
from html.parser import HTMLParser
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
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
        self.assertTrue(response.json()['saved'])
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
        self.item = self.items[Clothing.Status.BARTER]
        self.client.force_login(self.viewer)
        self.save_url = reverse('swap:save_interest', args=[self.item.pk])
        self.incoming_url = reverse('swap:requests_incoming')
        self.outgoing_url = reverse('swap:requests_outgoing')

    def send_request(self):
        response = self.client.post(self.save_url)
        self.assertEqual(response.status_code, 200)
        return SwapRequest.objects.get(pk=response.json()['request_id'])

    def counter(self, proposal, **fields):
        self.client.force_login(self.owner)
        return self.client.post(reverse('swap:counter_offer', args=[proposal.pk]), {
            'offered_item': self.own_item.pk, **fields,
        })

    def act(self, proposal, user, action, **fields):
        self.client.force_login(user)
        response = self.client.post(reverse('swap:update_request_status', args=[proposal.pk, action]), fields)
        proposal.refresh_from_db()
        return response

    def test_interested_creates_pending_request_without_selecting_own_item(self):
        proposal = self.send_request()
        self.assertEqual((proposal.sender, proposal.recipient, proposal.requested_item), (self.viewer, self.owner, self.item))
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)
        self.assertIsNone(proposal.offered_item)
        self.assertTrue(Interest.objects.filter(user=self.viewer, item=self.item).exists())
        self.assertFalse(Conversation.objects.exists())
        for user, page in ((self.viewer, self.outgoing_url), (self.owner, self.incoming_url)):
            self.client.force_login(user)
            response = self.client.get(page)
            self.assertContains(response, self.item.name)
            self.assertContains(response, 'No counter-offer selected yet.')
            self.assertNotContains(response, 'Item no longer available')
            self.assertNotContains(response, 'Accept offer')

    def test_request_identity_and_terms_cannot_be_forged_on_interest(self):
        self.client.post(self.save_url, {
            'sender': self.owner.pk, 'recipient': self.viewer.pk, 'status': 'completed',
            'offered_item': self.own_item.pk, 'top_up_payer': 'sender', 'top_up_amount': '50000',
        })
        proposal = SwapRequest.objects.get()
        self.assertEqual((proposal.sender, proposal.recipient), (self.viewer, self.owner))
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)
        self.assertIsNone(proposal.offered_item)
        self.assertIsNone(proposal.top_up_amount)

    def test_retries_reuse_request_in_every_active_stage(self):
        proposal = self.send_request()
        for status in ('pending', 'countered', 'accepted', 'in_progress'):
            SwapRequest.objects.filter(pk=proposal.pk).update(status=status)
            response = self.client.post(self.save_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['request_id'], proposal.pk)
            self.assertFalse(response.json()['created'])
            self.assertEqual(SwapRequest.objects.count(), 1)
        self.assertFalse(Message.objects.exists())

    def test_counter_form_lists_only_requesters_available_pieces(self):
        proposal = self.send_request()
        hidden = Clothing.objects.create(owner=self.viewer, name='Private piece', status=Clothing.Status.PERSONAL)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('swap:counter_offer', args=[proposal.pk]))
        self.assertEqual(list(response.context['offer_items']), [self.own_item])
        self.assertContains(response, self.own_item.name)
        self.assertContains(response, self.own_item.photo.url)
        self.assertNotContains(response, hidden.name)
        self.assertContains(response, 'Send counter-offer')
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

    def test_counter_selection_rejects_wrong_owner_and_unavailable_pieces(self):
        proposal = self.send_request()
        for value in (self.item.pk, 999999, 'invalid', ''):
            self.assertEqual(self.counter(proposal, offered_item=value).status_code, 400)
        for status in ('personal', 'donate', 'swapped'):
            Clothing.objects.filter(pk=self.own_item.pk).update(status=status)
            self.assertEqual(self.counter(proposal).status_code, 400)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)
        self.assertIsNone(proposal.offered_item)

    def test_counter_choice_and_top_up_are_validated_again_after_locking(self):
        from unittest.mock import patch
        from .forms import CounterOfferForm
        proposal = self.send_request()
        original = CounterOfferForm.is_valid
        def validate_then_change(form):
            result = original(form)
            Clothing.objects.filter(pk=self.own_item.pk).update(status=Clothing.Status.PERSONAL)
            return result
        with patch.object(CounterOfferForm, 'is_valid', validate_then_change):
            self.assertEqual(self.counter(proposal).status_code, 400)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

    def test_only_recipient_can_access_counter_form_and_submit(self):
        proposal = self.send_request()
        outsider = get_user_model().objects.create_user(username='counter_outsider')
        url = reverse('swap:counter_offer', args=[proposal.pk])
        for user in (self.viewer, outsider):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {'offered_item': self.own_item.pk}).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)

    def test_counter_post_requires_csrf_and_get_does_not_change_state(self):
        proposal = self.send_request()
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        url = reverse('swap:counter_offer', args=[proposal.pk])
        self.assertEqual(browser.post(url, {'offered_item': self.own_item.pk}).status_code, 403)
        self.assertEqual(browser.get(url).status_code, 200)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)
        self.assertEqual(browser.post(url, {
            'offered_item': self.own_item.pk,
            'csrfmiddlewaretoken': browser.cookies['csrftoken'].value,
        }).status_code, 302)
        self.assertEqual(browser.put(url, HTTP_X_CSRFTOKEN=browser.cookies['csrftoken'].value).status_code, 405)

    def test_counter_offer_needs_sender_decision_and_cannot_be_replaced_on_retry(self):
        proposal = self.send_request()
        self.assertRedirects(self.counter(proposal), self.incoming_url)
        proposal.refresh_from_db()
        original_time = proposal.countered_at
        self.assertIsNotNone(original_time)
        self.assertEqual(proposal.status, SwapRequest.Status.COUNTERED)
        self.assertEqual(proposal.offered_item, self.own_item)
        for action in ('accept', 'decline'):
            self.assertEqual(self.act(proposal, self.owner, action).status_code, 404)
        for action in ('start', 'complete'):
            self.act(proposal, self.viewer, action)
            self.assertEqual(proposal.status, SwapRequest.Status.COUNTERED)
        alternative = Clothing.objects.create(owner=self.viewer, name='Alternative', status=Clothing.Status.BARTER)
        self.counter(proposal, offered_item=alternative.pk)
        proposal.refresh_from_db()
        self.assertEqual(proposal.offered_item, self.own_item)
        self.assertEqual(proposal.countered_at, original_time)
        self.act(proposal, self.viewer, 'accept', offered_item=alternative.pk, status='completed')
        self.assertEqual(proposal.status, SwapRequest.Status.ACCEPTED)
        self.assertEqual(proposal.offered_item, self.own_item)
        self.assertEqual(self.item.status, Clothing.Status.BARTER)

    def test_pending_without_counter_cannot_be_accepted_or_completed(self):
        proposal = self.send_request()
        for user in (self.owner, self.viewer):
            for action in ('accept', 'start', 'complete'):
                self.act(proposal, user, action)
                self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

    def test_sender_can_decline_counter_and_either_party_can_cancel_it(self):
        for actor, action, status in ((self.viewer, 'decline', 'declined'), (self.owner, 'cancel', 'cancelled'), (self.viewer, 'cancel', 'cancelled')):
            self.client.force_login(self.viewer)
            proposal = self.send_request()
            self.counter(proposal)
            self.act(proposal, actor, action)
            self.assertEqual(proposal.status, status)
            self.act(proposal, self.viewer, 'accept')
            self.assertEqual(proposal.status, status)

    def test_empty_requester_closet_explains_next_step_without_exposing_private_items(self):
        proposal = self.send_request()
        Clothing.objects.filter(pk=self.own_item.pk).update(status=Clothing.Status.PERSONAL)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('swap:counter_offer', args=[proposal.pk]))
        self.assertContains(response, 'No available pieces')
        self.assertNotContains(response, 'Send counter-offer')
        self.assertNotContains(response, self.own_item.name)
        self.assertEqual(self.counter(proposal).status_code, 400)

    def test_unavailable_requested_piece_hides_details_and_rejects_counter(self):
        proposal = self.send_request()
        for status in ('personal', 'donate', 'swapped'):
            Clothing.objects.filter(pk=self.item.pk).update(status=status)
            response = self.counter(proposal)
            self.assertEqual(response.status_code, 400)
            self.assertNotContains(response, self.item.name, status_code=400)
            self.assertNotContains(response, self.item.photo.url, status_code=400)
        Clothing.objects.filter(pk=self.item.pk).update(owner=self.viewer, status=Clothing.Status.BARTER)
        self.assertEqual(self.counter(proposal).status_code, 400)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

    def test_deleted_requested_piece_preserves_request_and_can_be_declined(self):
        proposal = self.send_request()
        Clothing.objects.filter(pk=self.item.pk).update(photo='')
        self.item.delete()
        self.assertEqual(self.counter(proposal).status_code, 400)
        self.act(proposal, self.owner, 'decline')
        self.assertEqual(proposal.status, SwapRequest.Status.DECLINED)
        self.assertIsNone(proposal.requested_item)

    def test_removing_saved_interest_does_not_cancel_transaction(self):
        proposal = self.send_request()
        interest = Interest.objects.get(user=self.viewer, item=self.item)
        self.client.post(reverse('swap:remove_interest', args=[interest.pk]))
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)
        self.assertEqual(self.send_request().pk, proposal.pk)

    def test_existing_saved_piece_can_send_request_without_an_offer(self):
        interest = Interest.objects.create(user=self.viewer, item=self.item)
        url = reverse('swap:propose', args=[interest.pk])
        self.assertContains(self.client.get(url), 'Send request')
        self.assertFalse(SwapRequest.objects.exists())
        self.assertRedirects(self.client.post(url), self.outgoing_url)
        self.assertIsNone(SwapRequest.objects.get().offered_item)
        self.assertFalse(Conversation.objects.exists())

    def test_request_lists_are_private(self):
        proposal = self.send_request()
        self.assertFalse(self.client.get(self.incoming_url).context['swap_requests'])
        self.client.force_login(self.owner)
        self.assertFalse(self.client.get(self.outgoing_url).context['swap_requests'])
        outsider = get_user_model().objects.create_user(username='request_outsider')
        self.client.force_login(outsider)
        for url in (self.incoming_url, self.outgoing_url):
            response = self.client.get(url)
            self.assertFalse(response.context['swap_requests'])
            self.assertNotContains(response, self.item.name)
        for action in ('accept', 'decline', 'cancel', 'start', 'complete', 'keep'):
            self.assertEqual(self.act(proposal, outsider, action).status_code, 404)

    def test_counter_badge_and_actions_follow_whose_turn_it_is(self):
        proposal = self.send_request()
        self.client.force_login(self.owner)
        incoming = self.client.get(self.incoming_url)
        self.assertEqual(incoming.context['pending_incoming_count'], 1)
        self.assertContains(incoming, 'Choose counter-offer')
        self.counter(proposal)
        incoming = self.client.get(self.incoming_url)
        self.assertEqual(incoming.context['pending_request_count'], 0)
        self.assertNotContains(incoming, 'Accept counter-offer')
        self.client.force_login(self.viewer)
        outgoing = self.client.get(self.outgoing_url)
        self.assertEqual(outgoing.context['pending_outgoing_count'], 1)
        self.assertEqual(outgoing.context['pending_request_count'], 1)
        self.assertContains(outgoing, 'Outgoing (1)')
        self.assertContains(outgoing, 'Accept counter-offer')
        self.assertContains(outgoing, 'Decline counter-offer')
        self.act(proposal, self.viewer, 'accept')
        self.assertEqual(self.client.get(self.outgoing_url).context['pending_request_count'], 0)

    def test_complete_new_workflow_requires_start_and_both_confirmations(self):
        proposal = self.send_request()
        self.counter(proposal)
        self.act(proposal, self.viewer, 'accept')
        self.act(proposal, self.owner, 'complete')
        self.assertEqual(proposal.status, SwapRequest.Status.ACCEPTED)
        self.assertIsNone(proposal.recipient_confirmed_at)
        self.assertContains(self.client.get(self.incoming_url), 'Start exchange')
        self.act(proposal, self.owner, 'start')
        started_at = proposal.status_changed_at
        self.assertEqual(proposal.status, SwapRequest.Status.IN_PROGRESS)
        self.act(proposal, self.viewer, 'start')
        self.assertEqual(proposal.status_changed_at, started_at)
        self.act(proposal, self.viewer, 'complete')
        self.assertEqual(proposal.status, SwapRequest.Status.IN_PROGRESS)
        self.act(proposal, self.owner, 'complete')
        self.assertEqual(proposal.status, SwapRequest.Status.COMPLETED)
        for piece in (self.item, self.own_item):
            piece.refresh_from_db()
            self.assertEqual(piece.status, Clothing.Status.SWAPPED)
        self.assertFalse(Message.objects.exists())

    def test_start_requires_post_csrf_available_items_and_no_cancellation(self):
        proposal = self.send_request()
        self.counter(proposal)
        self.act(proposal, self.viewer, 'accept')
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        url = reverse('swap:update_request_status', args=[proposal.pk, 'start'])
        self.assertEqual(browser.get(url).status_code, 405)
        self.assertEqual(browser.post(url).status_code, 403)
        self.act(proposal, self.owner, 'cancel')
        self.act(proposal, self.viewer, 'start')
        self.assertEqual(proposal.status, SwapRequest.Status.ACCEPTED)
        self.act(proposal, self.viewer, 'keep')
        Clothing.objects.filter(pk=self.item.pk).update(status=Clothing.Status.PERSONAL)
        self.act(proposal, self.viewer, 'start')
        self.assertEqual(proposal.status, SwapRequest.Status.ACCEPTED)

    def test_counter_rechecks_availability_when_sender_accepts(self):
        proposal = self.send_request()
        self.counter(proposal)
        for piece in (self.item, self.own_item):
            for status in ('personal', 'donate', 'swapped'):
                Clothing.objects.filter(pk=piece.pk).update(status=status)
                self.act(proposal, self.viewer, 'accept')
                self.assertEqual(proposal.status, SwapRequest.Status.COUNTERED)
            Clothing.objects.filter(pk=piece.pk).update(status=Clothing.Status.BARTER)
        Clothing.objects.filter(pk=self.own_item.pk).update(owner=self.owner)
        self.act(proposal, self.viewer, 'accept')
        self.assertEqual(proposal.status, SwapRequest.Status.COUNTERED)

    def test_completed_exchange_closes_other_counter_offers(self):
        proposal = self.send_request()
        self.counter(proposal)
        outsider = get_user_model().objects.create_user(username='competing_requester')
        other_item = Clothing.objects.create(owner=outsider, name='Other piece', status='barter')
        competing = SwapRequest.objects.create(sender=outsider, recipient=self.owner, requested_item=self.item, offered_item=other_item, status='countered')
        self.act(proposal, self.viewer, 'accept')
        self.act(competing, outsider, 'accept')
        self.assertEqual(competing.status, SwapRequest.Status.COUNTERED)
        self.act(proposal, self.owner, 'start')
        self.act(proposal, self.viewer, 'complete')
        self.act(proposal, self.owner, 'complete')
        competing.refresh_from_db()
        self.assertEqual(competing.status, SwapRequest.Status.CANCELLED)

    def test_database_prevents_duplicate_active_request_across_stages(self):
        proposal = self.send_request()
        for status in ('pending', 'countered', 'accepted', 'in_progress'):
            SwapRequest.objects.filter(pk=proposal.pk).update(status=status)
            with self.assertRaises(IntegrityError), transaction.atomic():
                SwapRequest.objects.create(sender=self.viewer, recipient=self.owner, requested_item=self.item)

    def test_chat_can_still_be_opened_without_automatic_messages(self):
        proposal = self.send_request()
        conversation = Conversation.objects.create(user1=self.owner, user2=self.viewer)
        message = Message.objects.create(conversation=conversation, sender=self.owner, content='Hello!')
        interest = Interest.objects.get(user=self.viewer, item=self.item)
        url = reverse('swap:propose', args=[interest.pk])
        self.assertRedirects(self.client.post(url), reverse('chat:room', args=[conversation.pk]))
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(list(conversation.messages.all()), [message])
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.PENDING)

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
        self.assertContains(self.client.get(reverse('swap:interested')), 'Open chat')

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
            status=SwapRequest.Status.IN_PROGRESS,
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
                    status=SwapRequest.Status.IN_PROGRESS, sender_confirmed_at=None, recipient_confirmed_at=None,
                )
                Clothing.objects.filter(pk__in=[self.item.pk, self.own_item.pk]).update(status=Clothing.Status.BARTER)
                self.act(first, 'complete')
                self.assertEqual(self.proposal.status, SwapRequest.Status.IN_PROGRESS)
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
        self.assertEqual(self.proposal.status, SwapRequest.Status.IN_PROGRESS)

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
        other_request = SwapRequest.objects.create(sender=self.viewer, recipient=self.outsider, requested_item=self.third_item)
        self.client.force_login(self.outsider)
        url = reverse('swap:counter_offer', args=[other_request.pk])
        response = self.client.get(url)
        self.assertNotIn(self.own_item, response.context['form'].fields['offered_item'].queryset)
        self.assertEqual(self.client.post(url, {'offered_item': self.own_item.pk}).status_code, 400)
        other_request.refresh_from_db()
        self.assertIsNone(other_request.offered_item)
        self.assertEqual(other_request.status, SwapRequest.Status.PENDING)

    def test_cancellation_needs_both_people_and_releases_pieces(self):
        for first, second in ((self.viewer, self.owner), (self.owner, self.viewer)):
            with self.subTest(first=first.username):
                SwapRequest.objects.filter(pk=self.proposal.pk).update(
                    status=SwapRequest.Status.IN_PROGRESS,
                    cancellation_requested_by=None, cancellation_requested_at=None,
                )
                self.act(first, 'cancel')
                self.assertEqual(self.proposal.status, SwapRequest.Status.IN_PROGRESS)
                self.assertEqual(self.proposal.cancellation_requested_by_id, first.pk)
                self.act(first, 'cancel')
                self.assertEqual(self.proposal.status, SwapRequest.Status.IN_PROGRESS)
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
        self.assertEqual(self.proposal.status, SwapRequest.Status.IN_PROGRESS)
        self.assertIsNone(self.proposal.recipient_confirmed_at)
        self.act(self.viewer, 'keep')
        self.assertIsNone(self.proposal.cancellation_requested_by_id)
        self.assertIsNone(self.proposal.cancellation_requested_at)
        self.act(self.owner, 'complete')
        self.assertEqual(self.proposal.status, SwapRequest.Status.COMPLETED)

    def test_cancellation_can_be_withdrawn_by_requester(self):
        self.act(self.owner, 'cancel')
        self.act(self.owner, 'keep')
        self.assertEqual(self.proposal.status, SwapRequest.Status.IN_PROGRESS)
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
        self.assertEqual(self.proposal.status, SwapRequest.Status.IN_PROGRESS)
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
        self.assertEqual(self.proposal.status, SwapRequest.Status.IN_PROGRESS)
        self.assertIsNone(self.proposal.recipient_confirmed_at)
        self.own_item.refresh_from_db()
        self.assertEqual(self.own_item.status, Clothing.Status.BARTER)

    def test_ownership_change_blocks_completion(self):
        self.act(self.viewer, 'complete')
        Clothing.objects.filter(pk=self.own_item.pk).update(owner=self.outsider)
        self.act(self.owner, 'complete')
        self.assertEqual(self.proposal.status, SwapRequest.Status.IN_PROGRESS)
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


class SwapTopUpTests(SwapTestBase):
    def setUp(self):
        self.item = self.items[Clothing.Status.TOP_UP]
        self.new_request()

    def new_request(self):
        self.client.force_login(self.viewer)
        response = self.client.post(reverse('swap:save_interest', args=[self.item.pk]))
        self.proposal = SwapRequest.objects.get(pk=response.json()['request_id'])
        self.url = reverse('swap:counter_offer', args=[self.proposal.pk])
        self.client.force_login(self.owner)

    def submit(self, payer='sender', amount='50000'):
        return self.client.post(self.url, {
            'offered_item': self.own_item.pk,
            'top_up_payer': payer,
            'top_up_amount': amount,
        })

    def test_both_payer_choices_are_saved_and_shown_to_both_people(self):
        for payer in ('sender', 'recipient'):
            with self.subTest(payer=payer):
                self.new_request()
                response = self.submit(payer)
                proposal = SwapRequest.objects.get(status=SwapRequest.Status.COUNTERED)
                self.assertEqual(proposal.top_up_payer, payer)
                self.assertEqual(proposal.top_up_amount, Decimal('50000'))
                self.assertRedirects(response, reverse('swap:requests_incoming'))
                payer_user, payee = (self.viewer, self.owner) if payer == 'sender' else (self.owner, self.viewer)
                for user, page in ((self.viewer, 'swap:requests_outgoing'), (self.owner, 'swap:requests_incoming')):
                    self.client.force_login(user)
                    page_response = self.client.get(reverse(page))
                    self.assertContains(page_response, f'{payer_user.username} pays Rp 50.000 to {payee.username}.')
                    self.assertContains(page_response, 'Proposed terms')
                    if user == self.viewer:
                        self.assertContains(page_response, 'Accept swap &amp; top-up')
                proposal.status = SwapRequest.Status.DECLINED
                proposal.save(update_fields=['status'])
        self.assertFalse(Message.objects.exists())

    def test_no_top_up_supports_both_new_and_existing_form_submissions(self):
        for fields in ({}, {'top_up_payer': 'none', 'top_up_amount': ''}):
            with self.subTest(fields=fields):
                self.new_request()
                response = self.client.post(self.url, {'offered_item': self.own_item.pk, **fields})
                self.assertEqual(response.status_code, 302)
                proposal = SwapRequest.objects.get(status=SwapRequest.Status.COUNTERED)
                self.assertEqual(proposal.top_up_payer, SwapRequest.TopUpPayer.NONE)
                self.assertIsNone(proposal.top_up_amount)
                self.assertContains(self.client.get(reverse('swap:requests_incoming')), 'No top-up. Pieces only.')
                proposal.status = SwapRequest.Status.CANCELLED
                proposal.save(update_fields=['status'])

    def test_invalid_terms_do_not_change_request_or_create_chat(self):
        for payer, amount, field in (
            ('sender', '', 'top_up_amount'),
            ('recipient', '0', 'top_up_amount'),
            ('sender', '-500', 'top_up_amount'),
            ('sender', '1.50', 'top_up_amount'),
            ('sender', '1000000000000', 'top_up_amount'),
            ('sender', 'abc', 'top_up_amount'),
            ('sender', 'NaN', 'top_up_amount'),
            ('sender', '50.000', 'top_up_amount'),
            ('none', '50000', 'top_up_amount'),
            ('outsider', '50000', 'top_up_payer'),
        ):
            with self.subTest(payer=payer, amount=amount):
                response = self.submit(payer, amount)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.context['form'].errors)
                self.proposal.refresh_from_db()
                self.assertEqual(self.proposal.status, SwapRequest.Status.PENDING)
                self.assertIsNone(self.proposal.offered_item)
                self.assertIsNone(self.proposal.top_up_amount)
                self.assertFalse(Conversation.objects.exists())

    def test_two_barter_items_cannot_have_top_up_but_offered_top_up_item_can(self):
        self.item.status = Clothing.Status.BARTER
        self.item.save(update_fields=['status'])
        response = self.submit()
        self.assertEqual(response.status_code, 400)
        self.assertIn('top_up_payer', response.context['form'].errors)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, SwapRequest.Status.PENDING)
        self.own_item.status = Clothing.Status.TOP_UP
        self.own_item.save(update_fields=['status'])
        self.assertEqual(self.submit().status_code, 302)
        self.assertEqual(SwapRequest.objects.get().top_up_amount, Decimal('50000'))

    def test_invalid_form_keeps_the_selected_payer_and_amount(self):
        response = self.submit('recipient', '-1')
        self.assertContains(response, '<option value="recipient" selected>', status_code=400)
        self.assertEqual(response.context['form']['top_up_amount'].value(), '-1')
        self.assertContains(response, 'id="top-up-amount-errors"', status_code=400)

    def test_retry_cannot_overwrite_existing_counter_terms(self):
        self.submit()
        proposal = SwapRequest.objects.get()
        response = self.submit('recipient', '90000')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SwapRequest.objects.count(), 1)
        proposal.refresh_from_db()
        self.assertEqual(proposal.top_up_payer, 'sender')
        self.assertEqual(proposal.top_up_amount, Decimal('50000'))

    def test_accept_and_complete_preserve_original_terms_despite_posted_changes(self):
        self.submit('recipient')
        proposal = SwapRequest.objects.get()
        self.client.force_login(self.viewer)
        self.client.post(reverse('swap:update_request_status', args=[proposal.pk, 'accept']), {
            'top_up_payer': 'sender', 'top_up_amount': '1',
        })
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.ACCEPTED)
        self.client.post(reverse('swap:update_request_status', args=[proposal.pk, 'start']))
        response = self.client.get(reverse('swap:requests_outgoing'))
        self.assertContains(response, 'Agreed terms')
        self.assertContains(response, 'Make sure the agreed top-up has also been settled.')
        for user in (self.owner, self.viewer):
            self.client.force_login(user)
            self.client.post(reverse('swap:update_request_status', args=[proposal.pk, 'complete']))
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, SwapRequest.Status.COMPLETED)
        self.assertEqual(proposal.top_up_payer, 'recipient')
        self.assertEqual(proposal.top_up_amount, Decimal('50000'))
        self.assertContains(self.client.get(reverse('swap:requests_outgoing')), 'Rp 50.000')

    def test_cancelled_request_retains_terms_and_new_offer_can_change_them(self):
        self.submit()
        original = SwapRequest.objects.get()
        self.client.post(reverse('swap:update_request_status', args=[original.pk, 'cancel']))
        self.new_request()
        self.assertEqual(self.submit('recipient', '75000').status_code, 302)
        original.refresh_from_db()
        self.assertEqual(original.status, SwapRequest.Status.CANCELLED)
        self.assertEqual(original.top_up_amount, Decimal('50000'))
        latest = SwapRequest.objects.get(status=SwapRequest.Status.COUNTERED)
        self.assertEqual(latest.top_up_payer, 'recipient')
        self.assertEqual(latest.top_up_amount, Decimal('75000'))

    def test_database_rejects_inconsistent_terms(self):
        self.proposal.delete()
        for payer, amount in (('sender', None), ('recipient', 0), ('sender', -1), ('none', 10), ('invalid', 10)):
            with self.subTest(payer=payer, amount=amount):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    SwapRequest.objects.create(
                        sender=self.viewer, recipient=self.owner,
                        offered_item=self.own_item, requested_item=self.item,
                        top_up_payer=payer, top_up_amount=amount,
                    )


class SwapIncomingCountTests(SwapTestBase):
    def setUp(self):
        self.client.force_login(self.viewer)
        self.incoming = SwapRequest.objects.create(
            sender=self.owner, recipient=self.viewer,
            offered_item=self.items[Clothing.Status.TOP_UP], requested_item=self.own_item,
        )
        SwapRequest.objects.create(
            sender=self.viewer, recipient=self.owner,
            offered_item=self.own_item, requested_item=self.items[Clothing.Status.BARTER],
        )
        self.interest = Interest.objects.create(user=self.viewer, item=self.items[Clothing.Status.TOP_UP])

    def test_badge_counts_only_own_pending_incoming_on_all_swap_pages(self):
        SwapRequest.objects.create(
            sender=self.owner, recipient=self.viewer,
            offered_item=self.items[Clothing.Status.BARTER], requested_item=self.own_item,
            status=SwapRequest.Status.DECLINED,
        )
        pages = [reverse(name) for name in (
            'swap:index', 'swap:interested', 'swap:requests_incoming', 'swap:requests_outgoing',
        )] + [reverse('swap:propose', args=[self.interest.pk])]
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.context['pending_incoming_count'], 1)
                self.assertContains(response, 'aria-label="1 requests awaiting your response"')
        self.assertContains(self.client.get(reverse('swap:requests_incoming')), 'Incoming (1)')

    def test_reading_does_not_clear_badge_but_accepting_or_declining_does(self):
        for action in ('accept', 'decline'):
            with self.subTest(action=action):
                SwapRequest.objects.filter(pk=self.incoming.pk).update(status=SwapRequest.Status.PENDING)
                for _ in range(2):
                    self.assertEqual(self.client.get(reverse('swap:requests_incoming')).context['pending_incoming_count'], 1)
                self.client.post(reverse('swap:update_request_status', args=[self.incoming.pk, action]))
                response = self.client.get(reverse('swap:index'))
                self.assertEqual(response.context['pending_incoming_count'], 0)
                self.assertNotContains(response, 'class="swap-request-count"')

    def test_sender_cancellation_removes_count_and_other_users_cannot_see_it(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('swap:update_request_status', args=[self.incoming.pk, 'cancel']))
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('swap:index')).context['pending_incoming_count'], 0)
        outsider = get_user_model().objects.create_user(username='badge_outsider')
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse('swap:index')).context['pending_incoming_count'], 0)


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
