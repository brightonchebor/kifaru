from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PaymentHistoryMigrationTests(TransactionTestCase):
    def test_old_quotes_and_payment_records_are_preserved_for_review(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old = [node for node in latest if node[0] not in ('payment', 'booking')]
        old += [('booking', '0008_booking_discount_amount_booking_original_amount_and_more'),
                ('payment', '0005_remove_payment_authorization_url_and_more')]
        executor.migrate(old)
        try:
            apps = executor.loader.project_state(old).apps
            User = apps.get_model('users', 'User')
            Property = apps.get_model('properties', 'Property')
            Booking = apps.get_model('booking', 'Booking')
            Payment = apps.get_model('payment', 'Payment')
            admin = User.objects.create(email='admin@example.com', role='admin')
            member = User.objects.create(email='member@example.com', role='external')
            prop = Property.objects.create(name='Legacy', slug='legacy', location='Nyali',
                                            country='Kenya', price='100.00', description='Legacy')
            common = dict(property=prop, full_name='Legacy guest', email='guest@example.com',
                          phone='+32470123456', check_in=date(2027, 1, 1), check_out=date(2027, 1, 3), total_days=2)
            half = Booking.objects.create(**common, user=member, booking_reference='HALF',
                                          total_amount='200.00', original_amount='200.00', discount_amount='100.00')
            first = Payment.objects.create(booking=half, user=admin, payment_method='cash',
                                            amount='50.00', remaining_amount='150.00', payment_status='partial')
            free = Booking.objects.create(**common, booking_reference='FREE', total_amount='200.00',
                                          original_amount='200.00', discount_amount='200.00', status='confirmed')
            cancelled = Booking.objects.create(**common, booking_reference='CANCELLED', total_amount='200.00', status='cancelled')
            refund = Payment.objects.create(booking=cancelled, user=admin, payment_method='cash',
                                            amount='200.00', payment_status='refunded')
            pending = Booking.objects.create(**common, booking_reference='PENDING', total_amount='200.00')
            unverified = Payment.objects.create(booking=pending, user=admin, payment_method='cash',
                                                amount='200.00', payment_status='pending')
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
        apps = executor.loader.project_state(latest).apps
        Booking = apps.get_model('booking', 'Booking')
        Payment = apps.get_model('payment', 'Payment')
        Entry = apps.get_model('payment', 'PaymentTransaction')
        self.assertEqual(Booking.objects.get(pk=half.pk).total_amount, Decimal('100.00'))
        self.assertEqual(Booking.objects.get(pk=free.pk).total_amount, 0)
        migrated = Payment.objects.get(pk=first.pk)
        self.assertEqual(migrated.user_id, member.pk)
        self.assertEqual(migrated.recorded_by_id, admin.pk)
        self.assertEqual(migrated.amount, Decimal('50.00'))
        self.assertEqual(migrated.remaining_amount, Decimal('50.00'))
        migrated = Payment.objects.get(pk=refund.pk)
        self.assertEqual(migrated.payment_status, 'refund_pending')
        self.assertEqual(migrated.refunded_amount, 0)
        self.assertFalse(Entry.objects.filter(payment=migrated, kind='refund').exists())
        migrated = Payment.objects.get(pk=unverified.pk)
        self.assertEqual(migrated.amount, 0)
        self.assertEqual(Entry.objects.get(payment=migrated).kind, 'legacy')
        self.assertEqual(Entry.objects.get(payment=migrated).amount, Decimal('200.00'))
