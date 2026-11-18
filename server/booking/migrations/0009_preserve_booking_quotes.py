from decimal import Decimal
from django.db import migrations


def preserve_quotes(apps, schema_editor):
    Booking = apps.get_model('booking', 'Booking')
    alias = schema_editor.connection.alias
    for booking in Booking.objects.using(alias).all().iterator():
        original = booking.original_amount
        if original is None:
            original = booking.total_amount + booking.discount_amount
        total = max(original - booking.discount_amount, Decimal('0.00'))
        values = {'original_amount': original, 'total_amount': total}
        if total == 0 and booking.status == 'pending':
            values['status'] = 'confirmed'
        Booking.objects.using(alias).filter(pk=booking.pk).update(**values)


class Migration(migrations.Migration):
    dependencies = [('booking', '0008_booking_discount_amount_booking_original_amount_and_more')]
    operations = [migrations.RunPython(preserve_quotes, migrations.RunPython.noop)]
