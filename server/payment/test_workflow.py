import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from booking.models import Booking
from booking.views import BookingCancelView, BookingDetailView
from properties.models import Property
from payment.models import Payment, PaymentTransaction
from payment.views import (PaymentRecordView, PaymentDetailView, PaymentRefundView,
                           AdminPaymentListView, BookingPaymentView)


class ManualPaymentTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        User = get_user_model()
        self.admin = User.objects.create(email='admin@example.com', role='admin', is_staff=True)
        self.member = User.objects.create(email='member@example.com', role='external')
        self.prop = Property.objects.create(name='Payment test', location='Nyali', country='Kenya',
                                            price='100.00', description='Test')
        self.booking = self.make_booking()
        mail_patch = patch('payment.services.send_normal_email')
        self.mail = mail_patch.start()
        self.addCleanup(mail_patch.stop)
        cancellation_patch = patch('booking.views.send_normal_email')
        cancellation_patch.start()
        self.addCleanup(cancellation_patch.stop)

    def make_booking(self, user=None, status='pending', total=None):
        start = timezone.now().date() + timedelta(days=30)
        fields = dict(property=self.prop, user=user, full_name='Customer', email=user.email if user else 'guest@example.com',
                      phone='+32470123456', check_in=start, check_out=start + timedelta(days=2), total_days=2, status=status)
        if total is not None:
            fields.update(original_amount=Decimal(total), total_amount=Decimal(total))
        return Booking.objects.create(**fields)

    def request(self, view, method, data=None, actor='admin', **kwargs):
        req = getattr(self.factory, method)('/api/payments/', data or {}, format='json')
        if actor == 'admin':
            force_authenticate(req, self.admin)
        elif actor:
            force_authenticate(req, actor)
        with self.captureOnCommitCallbacks(execute=True):
            return view.as_view()(req, **kwargs)

    def receipt(self, amount='200.00', booking=None, **extra):
        data = dict(booking=(booking or self.booking).pk, amount=amount, payment_method='cash')
        data.update(extra)
        return self.request(PaymentRecordView, 'post', data)

    def test_full_payment_confirms_both_member_and_guest_and_returns_dashboard_data(self):
        for user in [None, self.member]:
            booking = self.make_booking(user)
            response = self.receipt(booking=booking)
            self.assertEqual(response.status_code, 201, response.data)
            payment = Payment.objects.get(pk=response.data['id'])
            booking.refresh_from_db()
            self.assertEqual(booking.status, 'confirmed')
            self.assertEqual(payment.user_id, user.pk if user else None)
            self.assertEqual(payment.recorded_by_id, self.admin.pk)
            self.assertEqual(payment.updated_by_id, self.admin.pk)
            self.assertEqual(payment.remaining_amount, 0)
            self.assertIsNotNone(payment.completed_at)
            self.assertEqual(response.data['guest_email'], booking.email)
            self.assertEqual(response.data['booking_reference'], booking.booking_reference)
            self.assertEqual(response.data['property_name'], self.prop.name)
            self.assertEqual(len(response.data['transactions']), 1)
            self.assertEqual(self.mail.call_args.args[0]['to_email'], booking.email)
            self.assertIn('CONFIRMED', self.mail.call_args.args[0]['email_subject'])

    def test_deposit_and_balance_are_separate_receipts_and_confirm_only_when_fully_paid(self):
        first = self.receipt('50.00', payment_status='partial', remaining_amount='150.00')
        self.assertEqual(first.status_code, 201, first.data)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending')
        self.assertEqual(first.data['remaining_amount'], '150.00')
        second = self.receipt('150.00', payment_status='completed')
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(first.data['id'], second.data['id'])
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'confirmed')
        self.assertEqual(second.data['amount'], '200.00')
        self.assertEqual(second.data['prepayment_amount'], '50.00')
        self.assertEqual([row['amount'] for row in second.data['transactions']], ['50.00', '150.00'])

    def test_patch_cumulative_balance_creates_receipt_and_sends_confirmation_once(self):
        first = self.receipt('50.00')
        key = str(uuid.uuid4())
        payload = {'amount': '200.00', 'payment_status': 'completed', 'remaining_amount': '0.00', 'idempotency_key': key}
        response = self.request(PaymentDetailView, 'patch', payload, pk=first.data['id'])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['amount'], '200.00')
        self.assertEqual(PaymentTransaction.objects.count(), 2)
        self.assertIn('CONFIRMED', self.mail.call_args.args[0]['email_subject'])
        count = self.mail.call_count
        response = self.request(PaymentDetailView, 'patch', payload, pk=first.data['id'])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(PaymentTransaction.objects.count(), 2)
        self.assertEqual(self.mail.call_count, count)

    def test_invalid_financial_values_are_rejected_without_records(self):
        for extra in [
            {'amount': '1.00', 'payment_status': 'completed'}, {'currency': 'USD'},
            {'amount': '201.00'}, {'remaining_amount': '12.00'},
            {'prepayment_amount': '-1.00'}, {'prepayment_amount': '1.00'},
            {'amount': '0.00'}, {'payment_status': 'refunded'},
            {'payment_method': 'bank_transfer'}, {'payment_method': 'mpesa'},
            {'remaining_amount': '-1.00'},
            {'completed_at': timezone.now().isoformat()},
        ]:
            with self.subTest(extra=extra):
                amount = extra.get('amount', '200.00')
                rest = {key: value for key, value in extra.items() if key != 'amount'}
                response = self.receipt(amount, **rest)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertFalse(Payment.objects.exists())
                self.assertFalse(PaymentTransaction.objects.exists())
        self.mail.assert_not_called()

    def test_receipts_cannot_be_reassigned_or_reopen_cancelled_bookings(self):
        response = self.receipt('50.00')
        other = self.make_booking(status='cancelled')
        response = self.request(PaymentDetailView, 'patch', {'booking': other.pk}, pk=response.data['id'])
        self.assertEqual(response.status_code, 400)
        response = self.receipt(booking=other)
        self.assertEqual(response.status_code, 400)
        other.refresh_from_db()
        self.assertEqual(other.status, 'cancelled')

    def test_free_booking_needs_no_payment(self):
        free = self.make_booking(status='confirmed', total='0.00')
        response = self.receipt('1.00', booking=free)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_general_booking_update_cannot_reopen_a_cancelled_booking(self):
        cancelled = self.make_booking(status='cancelled')
        response = self.request(BookingDetailView, 'patch', {'status': 'confirmed'}, pk=cancelled.pk)
        self.assertEqual(response.status_code, 400)
        cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, 'cancelled')

    def test_payment_and_booking_save_are_atomic(self):
        with patch.object(Booking, 'save', side_effect=RuntimeError('simulated booking save error')):
            with self.assertRaises(RuntimeError):
                self.receipt()
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(PaymentTransaction.objects.exists())
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending')
        self.mail.assert_not_called()

    def test_retry_and_duplicate_receipt_protection(self):
        key = str(uuid.uuid4())
        data = {'idempotency_key': key, 'payment_method': 'bank_transfer', 'bank_transfer_reference': 'BANK-001'}
        first = self.receipt('50.00', **data)
        self.assertEqual(first.status_code, 201, first.data)
        second = self.receipt('50.00', **data)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(PaymentTransaction.objects.count(), 1)
        self.assertEqual(self.mail.call_count, 1)
        other = self.make_booking()
        response = self.receipt('50.00', booking=other, payment_method='bank_transfer', bank_transfer_reference='bank-001')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(PaymentTransaction.objects.count(), 1)

    def test_permissions_are_checked_before_validating_booking_data(self):
        for actor in [None, self.member]:
            response = self.request(PaymentRecordView, 'post', {'booking': 99999}, actor=actor)
            self.assertIn(response.status_code, [401, 403])
        self.assertFalse(Payment.objects.exists())

    def test_cancellation_preserves_partial_receipt_and_flags_refund_review(self):
        first = self.receipt('50.00')
        response = self.request(BookingCancelView, 'post', {'reason': 'Changed plans'}, pk=self.booking.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['refund_initiated'])
        self.assertTrue(response.data['refund_pending'])
        payment = Payment.objects.get(pk=first.data['id'])
        self.assertEqual(payment.amount, Decimal('50.00'))
        self.assertEqual(payment.refunded_amount, 0)
        self.assertEqual(payment.payment_status, 'refund_pending')
        self.assertEqual(payment.remaining_amount, 0)
        self.assertFalse(PaymentTransaction.objects.filter(kind='refund').exists())

    def test_partial_and_full_actual_refunds_have_history_and_do_not_reconfirm_booking(self):
        first = self.receipt()
        self.request(BookingCancelView, 'post', {}, pk=self.booking.pk)
        payload = {'amount': '50.00', 'payment_method': 'cash', 'notes': 'Cancellation refund', 'refund_confirmed': True}
        response = self.request(PaymentRefundView, 'post', payload, pk=first.data['id'])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['payment_status'], 'partially_refunded')
        self.assertEqual(response.data['refundable_amount'], '150.00')
        payload['amount'] = '150.00'
        response = self.request(PaymentRefundView, 'post', payload, pk=first.data['id'])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['payment_status'], 'refunded')
        self.assertEqual(response.data['net_received'], '0.00')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'cancelled')
        self.assertEqual(PaymentTransaction.objects.filter(kind='refund').count(), 2)

    def test_unconfirmed_overlarge_and_active_booking_refunds_are_rejected(self):
        first = self.receipt()
        payload = {'amount': '50.00', 'notes': 'Refund', 'refund_confirmed': True}
        response = self.request(PaymentRefundView, 'post', payload, pk=first.data['id'])
        self.assertEqual(response.status_code, 400)
        self.request(BookingCancelView, 'post', {}, pk=self.booking.pk)
        for changes in [{'refund_confirmed': False}, {'amount': '201.00'}, {'notes': ''}]:
            response = self.request(PaymentRefundView, 'post', dict(payload, **changes), pk=first.data['id'])
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(PaymentTransaction.objects.filter(kind='refund').exists())

    def test_actual_refund_retry_does_not_duplicate_money_or_notification(self):
        first = self.receipt()
        self.request(BookingCancelView, 'post', {}, pk=self.booking.pk)
        payload = {'amount': '50.00', 'payment_method': 'cash', 'notes': 'Refund',
                   'refund_confirmed': True, 'idempotency_key': str(uuid.uuid4())}
        response = self.request(PaymentRefundView, 'post', payload, pk=first.data['id'])
        self.assertEqual(response.status_code, 201, response.data)
        sent = self.mail.call_count
        response = self.request(PaymentRefundView, 'post', payload, pk=first.data['id'])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(PaymentTransaction.objects.filter(kind='refund').count(), 1)
        self.assertEqual(self.mail.call_count, sent)

    def test_dashboard_filter_and_guest_search_return_booking_identity(self):
        self.receipt('50.00')
        other = self.make_booking(self.member)
        self.receipt(booking=other)
        response = self.request(AdminPaymentListView, 'get', {'booking': self.booking.pk})
        rows = response.data['results']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['booking'], self.booking.pk)
        self.assertEqual(rows[0]['guest_email'], 'guest@example.com')
        response = self.request(BookingPaymentView, 'get', booking_id=other.pk)
        self.assertEqual(response.data['user'], self.member.pk)

    def test_paid_bookings_and_immutable_receipts_cannot_be_deleted_or_edited(self):
        self.receipt()
        response = self.request(BookingDetailView, 'delete', {}, pk=self.booking.pk)
        self.assertEqual(response.status_code, 409)
        entry = PaymentTransaction.objects.get()
        entry.amount = Decimal('1.00')
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            entry.save()

    def test_receipt_metadata_cannot_be_overwritten_without_a_new_transfer(self):
        first = self.receipt('50.00', payment_method='bank_transfer', bank_transfer_reference='ORIGINAL')
        response = self.request(PaymentDetailView, 'patch', {'bank_transfer_reference': 'REPLACED'}, pk=first.data['id'])
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(PaymentTransaction.objects.get().reference, 'ORIGINAL')

    def test_dashboard_revenue_counts_actual_money_and_refunds_not_unpaid_quotes(self):
        from booking.reports import DashboardSummaryView, PaymentReportsView
        response = self.request(DashboardSummaryView, 'get')
        self.assertEqual(response.data['all_time']['revenue'], '0.00')
        self.assertEqual(response.data['all_time']['booking_value'], '200.00')
        self.assertEqual(response.data['pending_actions']['pending_payments'], 1)
        first = self.receipt('50.00')
        response = self.request(DashboardSummaryView, 'get')
        self.assertEqual(response.data['all_time']['revenue'], '50.00')
        self.request(BookingCancelView, 'post', {}, pk=self.booking.pk)
        self.request(PaymentRefundView, 'post', {
            'amount': '50.00', 'refund_confirmed': True, 'notes': 'Cancelled', 'payment_method': 'cash',
        }, pk=first.data['id'])
        response = self.request(DashboardSummaryView, 'get')
        self.assertEqual(response.data['all_time']['revenue'], '0.00')
        self.assertEqual(response.data['all_time']['refunded_amount'], '50.00')
        response = self.request(PaymentReportsView, 'get')
        self.assertEqual(response.data['summary']['received_amount'], '50.00')
        self.assertEqual(response.data['summary']['refunded_amount'], '50.00')
        self.assertEqual(response.data['summary']['net_received'], '0.00')

    def test_payment_report_groups_each_instalment_by_its_actual_method(self):
        from booking.reports import PaymentReportsView
        self.receipt('50.00', payment_method='bank_transfer', bank_transfer_reference='BANK-1')
        self.receipt('150.00', payment_method='mpesa', mpesa_receipt_number='MPESA-1')
        response = self.request(PaymentReportsView, 'get')
        amounts = {row['payment_method']: row['total_amount'] for row in response.data['by_method']}
        self.assertEqual(amounts['bank_transfer'], Decimal('50.00'))
        self.assertEqual(amounts['mpesa'], Decimal('150.00'))

    def test_reports_use_transfer_dates_including_later_instalments(self):
        from booking.reports import DashboardSummaryView, PaymentReportsView
        self.receipt('100.00', occurred_at=(timezone.now() - timedelta(days=40)).isoformat())
        self.receipt('100.00')
        response = self.request(DashboardSummaryView, 'get')
        self.assertEqual(response.data['today']['revenue'], '100.00')
        self.assertEqual(response.data['all_time']['revenue'], '200.00')
        response = self.request(PaymentReportsView, 'get', {'start_date': str(timezone.localdate())})
        self.assertEqual(response.data['summary']['received_amount'], '100.00')

    def test_swagger_documents_receipt_response_and_refund_route_without_errors(self):
        from django.urls import include, path
        from drf_yasg import openapi
        from drf_yasg.generators import OpenAPISchemaGenerator
        from rest_framework.request import Request
        from booking.reports import PaymentReportsView
        raw = self.factory.get('/swagger.json')
        force_authenticate(raw, self.admin)
        generator = OpenAPISchemaGenerator(
            info=openapi.Info(title='Payment API', default_version='v1'),
            patterns=[path('api/', include('payment.urls')),
                      path('api/reports/payments/', PaymentReportsView.as_view())],
        )
        with self.assertNoLogs('drf_yasg.inspectors.base', level='WARNING'):
            schema = generator.get_schema(request=Request(raw), public=True)
        record_path = next(key for key in schema.paths if key.endswith('/payments/record/'))
        reference = schema.paths[record_path]['post'].responses['201'].schema['$ref']
        fields = schema.definitions[reference.rsplit('/', 1)[1]].properties
        self.assertTrue({'id', 'booking_reference', 'guest_name', 'transactions'} <= set(fields))
        body = next(parameter['schema'] for parameter in schema.paths[record_path]['post'].parameters
                    if parameter['in'] == 'body')
        request_fields = schema.definitions[body['$ref'].rsplit('/', 1)[1]].required
        self.assertTrue({'booking', 'amount', 'payment_method'} <= set(request_fields))
        self.assertTrue(any(key.endswith('/refunds/') for key in schema.paths))
        report_path = next(key for key in schema.paths if key.endswith('/reports/payments/'))
        parameters = {parameter['name'] for parameter in schema.paths[report_path]['get'].parameters}
        self.assertTrue({'start_date', 'end_date', 'currency'} <= parameters)
