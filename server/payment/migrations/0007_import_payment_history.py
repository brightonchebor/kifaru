from decimal import Decimal
import json

from django.db import migrations


def import_history(apps, schema_editor):
    Payment = apps.get_model('payment', 'Payment')
    Entry = apps.get_model('payment', 'PaymentTransaction')
    alias = schema_editor.connection.alias
    seen = set()
    for payment in Payment.objects.using(alias).select_related('booking', 'user').all().iterator():
        booking = payment.booking
        actor_id = payment.user_id if payment.user and payment.user.role == 'admin' else None
        snapshot = json.dumps({
            'legacy_status': payment.payment_status, 'legacy_amount': str(payment.amount),
            'legacy_deposit': str(payment.prepayment_amount), 'legacy_balance': str(payment.remaining_amount),
            'legacy_user_id': payment.user_id,
        }, sort_keys=True)
        verified = payment.payment_status in ('partial', 'completed', 'refunded')
        received = payment.amount if verified else Decimal('0.00')
        if payment.amount > 0:
            kind = 'receipt' if verified else 'legacy'
            reference = (payment.bank_transfer_reference if payment.payment_method == 'bank_transfer'
                         else payment.mpesa_receipt_number if payment.payment_method == 'mpesa' else '') or ''
            key = f'{kind}:{payment.payment_method}:{reference.strip().upper()}' if reference else None
            if key in seen:
                key = None  # Retain pre-existing duplicate references for manual review.
            if key:
                seen.add(key)
            entry = Entry.objects.using(alias).create(
                payment_id=payment.pk, kind=kind, amount=payment.amount,
                currency=payment.currency, payment_method=payment.payment_method,
                reference=reference.strip(), reference_key=key, recorded_by_id=actor_id,
                occurred_at=payment.created_at,
                notes='Imported legacy aggregate; individual receipts were not previously stored. ' + snapshot,
            )
            Entry.objects.using(alias).filter(pk=entry.pk).update(created_at=payment.created_at)
        cancelled = booking.status == 'cancelled'
        remaining = Decimal('0.00') if cancelled else max(booking.total_amount - received, Decimal('0.00'))
        if payment.payment_status == 'refunded':
            # The old cancellation flow set this flag without recording an actual refund.
            status = 'refund_pending'
        elif cancelled and received > 0:
            status = 'refund_pending'
        elif received == 0:
            status = 'pending'
        else:
            status = 'completed' if remaining == 0 else 'partial'
        Payment.objects.using(alias).filter(pk=payment.pk).update(
            user_id=booking.user_id, recorded_by_id=actor_id, updated_by_id=actor_id,
            amount=received, refunded_amount=0, remaining_amount=remaining,
            prepayment_amount=received, payment_status=status,
            notes=((payment.notes or '') + '\nLegacy import: ' + snapshot).strip(),
        )


class Migration(migrations.Migration):
    dependencies = [('payment', '0006_payment_recorded_by_payment_refunded_amount_and_more')]
    operations = [migrations.RunPython(import_history, migrations.RunPython.noop)]
