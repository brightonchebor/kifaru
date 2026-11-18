from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from booking.models import Booking
from booking.views import BookingListCreateView, BookingDetailView
from promotions.models import PromoCode
from properties.models import Property, PropertyPricing, PropertyContact


class BookingQuoteTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.customer = get_user_model().objects.create(
            email='customer@example.com', first_name='Registered', last_name='Guest',
            phone_number='+32470123456', country_of_residence='Belgium', role='external',
        )
        self.prop = Property.objects.create(name='Quote test', location='Nyali', country='Kenya',
                                            price='100.00', description='Test')
        self.price = PropertyPricing.objects.create(property=self.prop, accommodation_type='full_apartment',
            guest_type='all', stay_type='short_term', number_of_guests=2, min_nights=1, max_nights=9,
            price_per_night='100.00')
        PropertyContact.objects.create(property=self.prop, name='Owner', email='owner@example.com')
        PromoCode.objects.create(code='HALF', discount_type='percentage', discount_value=50)
        PromoCode.objects.create(code='FREE', discount_type='full')
        email_patch = patch('booking.views.send_normal_email')
        self.email = email_patch.start()
        self.addCleanup(email_patch.stop)

    def submit(self, user=None, coupon=None, index=0):
        start = timezone.now().date() + timedelta(days=30 + index * 10)
        data = {
            'property': self.prop.pk, 'accommodation_type': 'full_apartment',
            'check_in': str(start), 'check_out': str(start + timedelta(days=2)),
            'number_of_guests': 2, 'number_of_adults': 2, 'number_of_children': 0,
        }
        if not user:
            data.update(full_name='Anonymous Guest', email='guest@example.com', phone='+32470123456')
        if coupon:
            data['promo_code'] = coupon
        request = self.factory.post('/api/bookings/', data, format='json')
        if user:
            force_authenticate(request, user)
        return BookingListCreateView.as_view()(request)

    def test_member_and_guest_quotes_with_no_partial_and_full_coupon(self):
        index = 0
        for user in [None, self.customer]:
            for coupon, total, status in [(None, '200.00', 'pending'), ('HALF', '100.00', 'pending'), ('FREE', '0.00', 'confirmed')]:
                with self.subTest(member=bool(user), coupon=coupon):
                    response = self.submit(user, coupon, index)
                    index += 1
                    self.assertEqual(response.status_code, 201, response.data)
                    booking = Booking.objects.get(pk=response.data['id'])
                    self.assertEqual(booking.total_amount, Decimal(total))
                    self.assertEqual(booking.original_amount, Decimal('200.00'))
                    self.assertEqual(booking.status, status)
                    self.assertEqual(booking.user_id, user.pk if user else None)
                    self.assertEqual(booking.email, user.email if user else 'guest@example.com')
                    if user:
                        self.assertEqual(booking.full_name, 'Registered Guest')
                    self.price.price_per_night = Decimal('100.00')
                    booking.special_requests = 'Changed notes'
                    booking.save()
                    booking.refresh_from_db()
                    self.assertEqual(booking.total_amount, Decimal(total))

    def test_saved_quote_does_not_change_when_current_rate_changes(self):
        response = self.submit(coupon='HALF')
        booking = Booking.objects.get(pk=response.data['id'])
        self.price.price_per_night = Decimal('999.00')
        self.price.save()
        booking.status = 'cancelled'
        booking.save()
        booking.refresh_from_db()
        self.assertEqual(booking.original_amount, Decimal('200.00'))
        self.assertEqual(booking.total_amount, Decimal('100.00'))

    def test_discounted_member_and_guest_pay_only_the_discounted_amount(self):
        from payment.views import PaymentRecordView
        admin = get_user_model().objects.create(email='admin@example.com', role='admin', is_staff=True)
        for index, user in enumerate([None, self.customer]):
            response = self.submit(user, coupon='HALF', index=index)
            booking = Booking.objects.get(pk=response.data['id'])
            request = self.factory.post('/api/payments/record/', {
                'booking': booking.pk, 'amount': '100.00', 'payment_method': 'cash',
            }, format='json')
            force_authenticate(request, admin)
            with patch('payment.services.send_normal_email'), self.captureOnCommitCallbacks(execute=True):
                response = PaymentRecordView.as_view()(request)
            self.assertEqual(response.status_code, 201, response.data)
            booking.refresh_from_db()
            self.assertEqual(booking.total_amount, Decimal('100.00'))
            self.assertEqual(booking.status, 'confirmed')

    def test_free_booking_emails_do_not_request_payment(self):
        response = self.submit(coupon='FREE')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.email.call_count, 2)
        for args in self.email.call_args_list:
            body = args.args[0]['email_body']
            self.assertIn('No payment is required', body)
            self.assertNotIn('Please contact the guest with your payment details', body)

    def test_invalid_and_exhausted_coupons_do_not_leave_extra_bookings(self):
        from promotions.models import PromoUsage
        response = self.submit(coupon='UNKNOWN')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Booking.objects.exists())
        self.assertFalse(PromoUsage.objects.exists())
        promo = PromoCode.objects.get(code='FREE')
        promo.max_uses = 1
        promo.save()
        self.assertEqual(self.submit(coupon='FREE').status_code, 201)
        response = self.submit(coupon='FREE', index=1)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(PromoUsage.objects.count(), 1)
        promo.refresh_from_db()
        self.assertEqual(promo.times_used, 1)

    def test_customer_cannot_confirm_or_change_the_accepted_reservation(self):
        response = self.submit(self.customer)
        booking = Booking.objects.get(pk=response.data['id'])
        for payload in [{'status': 'confirmed'}, {'number_of_guests': 1}]:
            request = self.factory.patch('/api/bookings/', payload, format='json')
            force_authenticate(request, self.customer)
            response = BookingDetailView.as_view()(request, pk=booking.pk)
            self.assertEqual(response.status_code, 400, response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending')
        self.assertEqual(booking.number_of_guests, 2)
