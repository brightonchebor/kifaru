from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import include, path, resolve
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from booking.models import Booking
from booking.views import UserBookingsView, BookingDetailView, BookingCancelView
from payment.models import Payment
from payment.views import UserPaymentsView, PaymentRecordView, PaymentRefundView
from properties.models import Property
from promotions.models import PromoCode


class CustomerPaymentTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        User = get_user_model()
        self.member = User.objects.create(email='member@example.com', role='external')
        self.other = User.objects.create(email='other@example.com', role='external')
        self.admin = User.objects.create(email='admin@example.com', role='admin', is_staff=True)
        self.prop = Property.objects.create(name='Customer payment test', location='Nyali', country='Kenya',
                                            price='100.00', description='Test')
        for module in ['payment.services.send_normal_email', 'booking.views.send_normal_email']:
            mock = patch(module)
            mock.start()
            self.addCleanup(mock.stop)

    def booking(self, user='member', **extra):
        if user == 'member':
            user = self.member
        start = timezone.localdate() + timedelta(days=30)
        fields = dict(user=user, property=self.prop, full_name='Customer',
                      email=user.email if user else self.member.email, phone='+32470123456',
                      check_in=start, check_out=start + timedelta(days=2), total_days=2)
        fields.update(extra)
        return Booking.objects.create(**fields)

    def request(self, view, user='member', method='get', data=None, **kwargs):
        if user == 'member':
            user = self.member
        raw = getattr(self.factory, method)('/api/my-payments/', data or {}, format='json')
        if user:
            force_authenticate(raw, user)
        with self.captureOnCommitCallbacks(execute=True):
            return view.as_view()(raw, **kwargs)

    def receipt(self, booking, amount):
        response = self.request(PaymentRecordView, self.admin, 'post', {
            'booking': booking.pk, 'amount': amount, 'payment_method': 'cash',
            'notes': 'INTERNAL ADMIN NOTE',
        })
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def rows(self, view=UserPaymentsView, user='member', data=None):
        response = self.request(view, user, data=data)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_unpaid_booking_is_visible_before_a_payment_record_exists(self):
        booking = self.booking()
        row = self.rows()[0]
        self.assertEqual(row['booking'], booking.pk)
        self.assertEqual(row['booking_reference'], booking.booking_reference)
        self.assertEqual(row['booking_status'], 'pending')
        self.assertEqual(row['payment_status'], 'pending')
        self.assertIsNone(row['payment_id'])
        self.assertEqual(row['currency'], 'EUR')
        self.assertEqual(row['amount_paid'], '0.00')
        self.assertEqual(row['remaining_amount'], '200.00')
        self.assertEqual(row['transactions'], [])
        self.assertFalse(Payment.objects.exists())

    def test_customer_reads_fresh_partial_and_paid_status_after_admin_records_receipts(self):
        booking = self.booking()
        self.receipt(booking, '50.00')
        row = self.rows()[0]
        self.assertEqual(row['payment_status'], 'partial')
        self.assertEqual(row['amount_paid'], '50.00')
        self.assertEqual(row['remaining_amount'], '150.00')
        self.assertEqual(row['booking_status'], 'pending')
        self.assertEqual(len(row['transactions']), 1)
        self.receipt(booking, '150.00')
        row = self.rows()[0]
        self.assertEqual(row['payment_status'], 'completed')
        self.assertEqual(row['amount_paid'], '200.00')
        self.assertEqual(row['remaining_amount'], '0.00')
        self.assertEqual(row['booking_status'], 'confirmed')
        self.assertEqual(len(row['transactions']), 2)

    def test_my_bookings_and_detail_expose_the_same_payment_state(self):
        booking = self.booking()
        for amount, expected in [(None, 'pending'), ('50.00', 'partial'), ('150.00', 'completed')]:
            if amount:
                self.receipt(booking, amount)
            payments = self.rows()[0]
            bookings = self.rows(UserBookingsView)[0]
            detail = self.request(BookingDetailView, pk=booking.pk)
            self.assertEqual(detail.status_code, 200, detail.data)
            for response in [bookings, detail.data]:
                self.assertEqual(response['payment_status'], expected)
                for key in ['payment_id', 'amount_paid', 'refunded_amount', 'net_received', 'remaining_amount', 'currency']:
                    self.assertEqual(response[key], payments[key])

    def test_free_coupon_booking_is_not_shown_as_awaiting_payment(self):
        promo = PromoCode.objects.create(code='FREE', discount_type='full')
        booking = self.booking(promo_code=promo, original_amount=Decimal('200.00'),
                               discount_amount=Decimal('200.00'), status='confirmed')
        row = self.rows()[0]
        self.assertEqual(row['payment_status'], 'not_required')
        self.assertEqual(row['total_amount'], '0.00')
        self.assertEqual(row['remaining_amount'], '0.00')
        self.assertIsNone(row['payment_id'])
        self.assertFalse(Payment.objects.exists())
        detail = self.request(BookingDetailView, pk=booking.pk)
        self.assertEqual(detail.data['payment_status'], 'not_required')
        self.assertEqual(self.rows(UserBookingsView)[0]['payment_status'], 'not_required')

    def test_other_accounts_and_guests_with_the_same_email_are_never_included(self):
        mine = self.booking()
        other = self.booking(self.other)
        guest = self.booking(None)
        self.receipt(other, '200.00')
        self.receipt(guest, '200.00')
        for view in [UserPaymentsView, UserBookingsView]:
            rows = self.rows(view, data={'user': self.other.pk, 'booking': other.pk, 'email': self.member.email})
            key = 'booking' if view is UserPaymentsView else 'id'
            self.assertEqual([row[key] for row in rows], [mine.pk])
        # The admin who recorded payments still gets only their personal bookings here.
        self.assertEqual(self.rows(user=self.admin), [])

    def test_admin_account_can_read_its_own_personal_payments(self):
        mine = self.booking(self.admin)
        self.booking(self.member)
        self.assertEqual([row['booking'] for row in self.rows(user=self.admin)], [mine.pk])

    def test_history_does_not_expose_admin_notes_or_staff_ids(self):
        booking = self.booking()
        self.receipt(booking, '50.00')
        row = self.rows()[0]
        for field in ['notes', 'recorded_by', 'updated_by', 'user']:
            self.assertNotIn(field, row)
        for entry in row['transactions']:
            self.assertNotIn('notes', entry)
            self.assertNotIn('recorded_by', entry)
        self.assertNotIn('INTERNAL ADMIN NOTE', str(row))

    def test_cancelled_unpaid_booking_has_no_balance_due(self):
        booking = self.booking(status='cancelled')
        row = self.rows()[0]
        self.assertEqual(row['booking_status'], 'cancelled')
        self.assertEqual(row['payment_status'], 'cancelled')
        self.assertEqual(row['remaining_amount'], '0.00')
        self.assertIsNone(row['payment_id'])

    def test_refund_review_and_actual_refund_states_are_visible(self):
        booking = self.booking()
        summary = self.receipt(booking, '200.00')
        response = self.request(BookingCancelView, self.admin, 'post', pk=booking.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.rows()[0]['payment_status'], 'refund_pending')
        for amount, expected in [('50.00', 'partially_refunded'), ('150.00', 'refunded')]:
            response = self.request(PaymentRefundView, self.admin, 'post', {
                'amount': amount, 'refund_confirmed': True, 'payment_method': 'cash',
                'notes': 'INTERNAL REFUND NOTE',
            }, pk=summary['id'])
            self.assertEqual(response.status_code, 201, response.data)
            row = self.rows()[0]
            self.assertEqual(row['payment_status'], expected)
            self.assertEqual(row['remaining_amount'], '0.00')
            self.assertNotIn('INTERNAL REFUND NOTE', str(row))
        self.assertEqual(row['refunded_amount'], '200.00')
        self.assertEqual(row['net_received'], '0.00')

    def test_authentication_is_required_and_writes_are_not_allowed(self):
        booking = self.booking()
        response = self.request(UserPaymentsView, None)
        self.assertIn(response.status_code, [401, 403])
        response = self.request(UserPaymentsView, method='post', data={'booking': booking.pk, 'amount': '200.00'})
        self.assertEqual(response.status_code, 405)
        self.assertFalse(Payment.objects.exists())

    def test_both_customer_payment_urls_resolve_to_the_same_view(self):
        urls = (path('api/', include('payment.urls')),)
        for url in ['/api/my-payments/', '/api/payments/my-payments/']:
            self.assertIs(resolve(url, urlconf=urls).func.view_class, UserPaymentsView)

    def test_list_query_count_does_not_grow_per_booking(self):
        self.receipt(self.booking(), '50.00')
        with CaptureQueriesContext(connection) as first:
            self.rows()
        for _ in range(4):
            self.receipt(self.booking(), '50.00')
        with CaptureQueriesContext(connection) as more:
            self.rows()
        self.assertEqual(len(first), len(more))
