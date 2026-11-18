"""The single write path for verified manual receipts and actual refunds."""

from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from booking.models import Booking
from users.utils import send_normal_email
from .models import Payment, PaymentTransaction


ZERO = Decimal('0.00')


def booking_currency():
    return getattr(settings, 'DEFAULT_CURRENCY', 'EUR').upper()


def _notify(payment, kind, entry=None):
    booking = payment.booking
    if kind == 'refund':
        subject = f'Refund recorded — {booking.booking_reference}'
        message = f'A refund of {payment.currency} {entry.amount} has been recorded as returned to you.'
    elif payment.payment_status == 'completed':
        subject = (f'Booking CONFIRMED — {booking.booking_reference}' if booking.status == 'confirmed'
                   else f'Payment received — {booking.booking_reference}')
        message = ('Your booking is confirmed and the full amount has been received.'
                   if booking.status == 'confirmed' else 'The full amount has been received.')
    else:
        subject = f'Payment received — {booking.booking_reference}'
        message = 'Your payment has been recorded. Your booking awaits full payment.'
    body = (
        f'Dear {booking.full_name},\n\n{message}\n\n'
        f'Booking Reference: {booking.booking_reference}\n'
        f'Property: {booking.property.name}\n'
        f'Check-in: {booking.check_in:%d %b %Y}\n'
        f'Check-out: {booking.check_out:%d %b %Y}\n'
        f'Total booking price: {payment.currency} {booking.total_amount}\n'
        f'Total received: {payment.currency} {payment.amount}\n'
        f'Total refunded: {payment.currency} {payment.refunded_amount}\n'
        f'Balance due: {payment.currency} {payment.remaining_amount}\n'
    )
    recipients = [booking.email]
    if kind == 'refund':
        recipients += list(booking.property.contacts.exclude(email='').values_list('email', flat=True))
    for email in dict.fromkeys(recipients):
        send_normal_email({'to_email': email, 'email_subject': subject, 'email_body': body})


def refresh_summary(payment, actor=None, *, event=None, entry=None):
    """Recompute balances from immutable entries; caller holds the booking lock."""
    booking = payment.booking
    totals = payment.transactions.values('kind').annotate(total=Sum('amount'))
    totals = {row['kind']: row['total'] for row in totals}
    payment.amount = totals.get('receipt', ZERO)
    payment.refunded_amount = totals.get('refund', ZERO)
    net = payment.net_received
    cancelled = booking.status == 'cancelled'
    payment.remaining_amount = ZERO if cancelled else max(booking.total_amount - net, ZERO)
    receipts = payment.transactions.filter(kind='receipt')
    first, latest = receipts.first(), receipts.last()
    payment.prepayment_amount = first.amount if first else ZERO
    if latest:
        payment.payment_method = latest.payment_method
        if latest.payment_method == 'bank_transfer':
            payment.bank_transfer_reference = latest.reference
        elif latest.payment_method == 'mpesa':
            payment.mpesa_receipt_number = latest.reference
    if payment.refunded_amount:
        payment.payment_status = 'refunded' if net == 0 else 'partially_refunded'
    elif cancelled and net > 0:
        payment.payment_status = 'refund_pending'
    elif payment.amount == 0:
        payment.payment_status = 'pending'
    else:
        payment.payment_status = 'completed' if payment.remaining_amount == 0 else 'partial'
    if payment.payment_status == 'completed' and payment.completed_at is None:
        payment.completed_at = timezone.now()
    payment.user_id = booking.user_id
    if actor:
        payment.updated_by = actor
    payment.save()
    confirmed = False
    if booking.status == 'pending' and booking.total_amount > 0 and payment.payment_status == 'completed':
        booking.status = 'confirmed'
        booking.save(update_fields=['status'])
        confirmed = True
    if event or confirmed:
        transaction.on_commit(lambda: _notify(payment, event or 'receipt', entry), robust=True)
    return payment


def _check_request(data, *, received, refunded, booking, first_amount):
    remaining = ZERO if booking.status == 'cancelled' else booking.total_amount - (received - refunded)
    expected_status = ('completed' if remaining == 0 else 'partial') if received else 'pending'
    if data.get('payment_status') in ('refunded', 'partially_refunded', 'refund_pending'):
        raise ValidationError({'payment_status': 'Record actual refunds through the refunds endpoint after returning the money.'})
    if 'payment_status' in data and data['payment_status'] != expected_status:
        raise ValidationError({'payment_status': f'The recorded amounts require status {expected_status}.'})
    if data.get('remaining_amount') is not None and data['remaining_amount'] != remaining:
        raise ValidationError({'remaining_amount': f'The calculated remaining balance is {remaining}.'})
    if data.get('prepayment_amount') is not None and data['prepayment_amount'] != first_amount:
        raise ValidationError({'prepayment_amount': f'The first recorded payment is {first_amount}.'})


def _entry(payment, actor, kind, amount, data):
    method = data.get('payment_method', payment.payment_method)
    reference = (data.get('reference') or (
        data.get('bank_transfer_reference') if method == 'bank_transfer' else
        data.get('mpesa_receipt_number') if method == 'mpesa' else ''
    ) or '').strip()
    if method in ('bank_transfer', 'mpesa') and not reference:
        field = 'bank_transfer_reference' if method == 'bank_transfer' else 'mpesa_receipt_number'
        raise ValidationError({field: 'Supply the reference for this transfer.'})
    if reference and PaymentTransaction.objects.filter(
        kind=kind, payment_method=method, reference__iexact=reference,
    ).exists():
        raise ValidationError({'reference': 'This transfer reference has already been recorded.'})
    try:
        with transaction.atomic():
            return PaymentTransaction.objects.create(
                payment=payment, kind=kind, amount=amount, currency=payment.currency,
                payment_method=method, reference=reference, recorded_by=actor,
                occurred_at=data.get('occurred_at', timezone.now()), notes=data.get('notes') or '',
                idempotency_key=data.get('idempotency_key'),
            )
    except IntegrityError as exc:
        raise ValidationError({'reference': 'This transfer reference or request key has already been recorded.'}) from exc


def _retry(data, booking, kind, amount, *, cumulative=False):
    key = data.get('idempotency_key')
    if not key:
        return None
    existing = PaymentTransaction.objects.filter(idempotency_key=key).select_related('payment').first()
    if existing:
        method = data.get('payment_method', existing.payment_method)
        reference = (data.get('reference') or data.get('bank_transfer_reference')
                     or data.get('mpesa_receipt_number') or '').strip()
        recorded_amount = existing.amount
        if cumulative:
            recorded_amount = existing.payment.transactions.filter(kind='receipt', pk__lte=existing.pk).aggregate(total=Sum('amount'))['total']
        if (existing.payment.booking_id != booking.pk or existing.kind != kind
                or recorded_amount != amount or existing.payment_method != method
                or existing.reference.upper() != reference.upper()
                or existing.currency != data.get('currency', existing.currency).upper()):
            raise ValidationError({'idempotency_key': 'This key belongs to a different payment request.'})
        return existing.payment
    return None


@transaction.atomic
def record_receipt(booking_id, actor, data, *, payment_id=None, cumulative=False):
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    payment = Payment.objects.select_for_update().filter(booking=booking).first()
    if payment_id is not None and (payment is None or payment.pk != payment_id):
        raise ValidationError({'booking': 'A payment cannot be moved to another booking.'})
    old_amount = payment.amount if payment else ZERO
    requested = data.get('amount', old_amount)
    delta = requested - old_amount if cumulative else requested
    retry = _retry(data, booking, 'receipt', requested, cumulative=cumulative)
    if retry:
        return retry
    if booking.status == 'cancelled' and delta > 0:
        raise ValidationError({'booking': 'Cannot record a new receipt for a cancelled booking.'})
    if booking.total_amount == 0 and delta > 0:
        raise ValidationError({'booking': 'This booking is free; no payment is required.'})
    if delta < 0:
        raise ValidationError({'amount': 'Receipts cannot be reduced. Record a refund after cancelling the booking.'})
    if payment and delta == 0:
        if data.get('payment_status') == payment.payment_status:
            data = dict(data)
            data.pop('payment_status')
        for field in ('payment_method', 'bank_transfer_reference', 'mpesa_receipt_number'):
            if field in data and (data[field] or '') != (getattr(payment, field) or ''):
                raise ValidationError({field: 'Existing receipt details cannot be overwritten. Supply details with a new receipt.'})
        if 'reference' in data:
            last = payment.transactions.filter(kind='receipt').last()
            if data['reference'] != (last.reference if last else ''):
                raise ValidationError({'reference': 'Existing receipt details cannot be overwritten.'})
    currency = data.get('currency', payment.currency if payment else booking_currency()).upper()
    if currency != booking_currency() or (payment and payment.currency != currency):
        raise ValidationError({'currency': f'Booking payments must be recorded in {booking_currency()}.'})
    refunded = payment.refunded_amount if payment else ZERO
    if delta > 0 and refunded > 0:
        raise ValidationError({'booking': 'Cannot add receipts to a refunded booking.'})
    if old_amount + delta - refunded > booking.total_amount:
        raise ValidationError({'amount': 'Payment exceeds the booking balance.'})
    first = payment.transactions.filter(kind='receipt').first() if payment else None
    if delta > 0 or booking.status != 'cancelled':
        _check_request(data, received=old_amount + delta, refunded=refunded,
                       booking=booking, first_amount=first.amount if first else delta)
    elif 'payment_status' in data:
        raise ValidationError({'payment_status': 'Refund status is managed through the refunds endpoint.'})
    if payment is None:
        payment = Payment.objects.create(
            booking=booking, user_id=booking.user_id, recorded_by=actor, updated_by=actor,
            amount=ZERO, currency=currency, payment_method=data['payment_method'],
        )
    if 'notes' in data:
        payment.notes = data['notes']
    if 'mpesa_phone_number' in data:
        payment.mpesa_phone_number = data['mpesa_phone_number']
    entry = _entry(payment, actor, 'receipt', delta, data) if delta > 0 else None
    return refresh_summary(payment, actor, event='receipt' if entry else None, entry=entry)


@transaction.atomic
def record_refund(payment_id, actor, data):
    booking_id = Payment.objects.values_list('booking_id', flat=True).get(pk=payment_id)
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    payment.booking = booking
    retry = _retry(data, booking, 'refund', data['amount'])
    if retry:
        return retry
    if booking.status != 'cancelled':
        raise ValidationError({'booking': 'Cancel the booking before recording its refund.'})
    if not data.get('refund_confirmed'):
        raise ValidationError({'refund_confirmed': 'Confirm that the money has actually been returned.'})
    if data.get('currency', payment.currency).upper() != payment.currency:
        raise ValidationError({'currency': 'Refund currency must match the original payment.'})
    if data['amount'] > payment.net_received:
        raise ValidationError({'amount': 'Refund exceeds the remaining amount received.'})
    if not (data.get('notes') or '').strip():
        raise ValidationError({'notes': 'Supply a refund reason.'})
    entry = _entry(payment, actor, 'refund', data['amount'], data)
    return refresh_summary(payment, actor, event='refund', entry=entry)
