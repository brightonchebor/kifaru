"""
Script to populate Kifaru Impact Retreat data
Run with: python manage.py shell < populate_data.py
"""
from decimal import Decimal
from properties.models import (
    Property, PropertyPricing, PropertyFeature, PropertyContact,
    PropertyNetwork
)

print("Starting Kifaru data population...")
print("This will create sample data for all models")

# Create Properties
print("\n=== Creating Properties ===")
properties_data = {
    'brussels': {
        'name': 'Tech & Bed Kifaru Brussels',
        'slug': 'tech-bed-kifaru-brussels',
        'description': 'A luxurious apartment in Brussels with stunning park views, perfect for business travelers and digital nomads.',
        'location': 'Brussels, Belgium',
        'country': 'Belgium',
        'property_category': 'urban',
        'price': Decimal('180.00'),
        'bedrooms': 3,
        'bathrooms': 2,
        'square_meters': 120,
        'max_guests': 6,
        'min_nights': 2,
        'check_in_time': '15:00',
        'check_out_time': '10:30',
        'prepayment_percentage': 50,
        'cancellation_days': 30,
        'wifi_password': 'Kifaru2019',
    },
    'north_sea': {
        'name': 'Ocean Kifaru North-Sea',
        'slug': 'ocean-kifaru-north-sea',
        'description': 'Beachfront apartment in Cadzand-Bad, Netherlands, offering serene ocean views and a private terrace.',
        'location': 'Cadzand-Bad, Netherlands',
        'country': 'Netherlands',
        'property_category': 'beachfront',
        'price': Decimal('171.00'),
        'bedrooms': 2,
        'bathrooms': 1,
        'square_meters': 85,
        'terrace_size': 30,
        'max_guests': 4,
        'min_nights': 3,
        'check_in_time': '15:00',
        'check_out_time': '10:30',
        'prepayment_percentage': 50,
        'cancellation_days': 30,
        'wifi_password': 'Kifaru2019',
    },
    'msambweni': {
        'name': 'Ocean Kifaru Indian-Ocean',
        'slug': 'ocean-kifaru-indian-ocean',
        'description': 'Exclusive beach resort in Msambweni, Kenya, with private beach access and infinity pool.',
        'location': 'Msambweni, Kenya',
        'country': 'Kenya',
        'property_category': 'beachfront',
        'price': Decimal('350.00'),
        'bedrooms': 4,
        'bathrooms': 3,
        'square_meters': 250,
        'max_guests': 8,
        'min_nights': 3,
        'check_in_time': '15:00',
        'check_out_time': '10:30',
        'prepayment_percentage': 50,
        'cancellation_days': 30,
        'wifi_password': 'Kifaru2019',
    },
    'marble': {
        'name': 'Kifaru Marble Inn Mombasa',
        'slug': 'kifaru-marble-inn-mombasa',
        'description': 'Elegant guesthouse in Nyali, Mombasa, featuring marble finishes and proximity to beaches.',
        'location': 'Nyali, Mombasa, Kenya',
        'country': 'Kenya',
        'property_category': 'urban',
        'price': Decimal('125.00'),
        'bedrooms': 3,
        'bathrooms': 2,
        'square_meters': 150,
        'max_guests': 6,
        'min_nights': 2,
        'check_in_time': '15:00',
        'check_out_time': '10:30',
        'prepayment_percentage': 50,
        'cancellation_days': 30,
        'wifi_password': 'Kifaru2019',
    },
    'hub': {
        'name': 'Close the Gap HUB',
        'slug': 'close-the-gap-hub',
        'description': 'Management suite with workspace in Nyali, Mombasa, for entrepreneurs and remote workers.',
        'location': 'Nyali, Mombasa, Kenya',
        'country': 'Kenya',
        'property_category': 'coworking',
        'price': Decimal('75.00'),  # PDF shows €75/night for short stay
        'bedrooms': 1,
        'bathrooms': 1,
        'square_meters': 350,  # 350m² rooftop terrace mentioned in PDF
        'max_guests': 2,
        'min_nights': 4,
        'check_in_time': '15:00',
        'check_out_time': '10:30',
        'prepayment_percentage': 50,
        'cancellation_days': 7,
        'wifi_password': 'Kifaru2019',
    },
}

props = {}
for key, data in properties_data.items():
    prop, created = Property.objects.get_or_create(slug=data['slug'], defaults=data)
    props[key] = prop
    print(f"{'Created' if created else 'Exists'}: {prop.name}")

# Create Property Pricing - EXACT PDF VALUES
print("\n=== Creating Property Pricing ===")
pricing_data = [
    # BRUSSELS - PDF Page 7
    {'prop': 'brussels', 'acc_type': 'master_bedroom', 'guest': 'international', 'stay': 'long_term', 'min_nights': 10, 'price': '150', 'weekly': '1200', 'breakfast': False, 'fullboard': False},
    {'prop': 'brussels', 'acc_type': 'master_bedroom', 'guest': 'international', 'stay': 'short_term', 'min_nights': 1, 'max_nights': 9, 'price': '200', 'weekly': None, 'breakfast': False, 'fullboard': False},
    {'prop': 'brussels', 'acc_type': 'full_apartment', 'guest': 'international', 'stay': 'long_term', 'min_nights': 10, 'price': '200', 'weekly': '1400', 'breakfast': False, 'fullboard': False},
    {'prop': 'brussels', 'acc_type': 'full_apartment', 'guest': 'international', 'stay': 'short_term', 'min_nights': 1, 'max_nights': 9, 'price': '250', 'weekly': None, 'breakfast': False, 'fullboard': False},
    
    # NORTH SEA - PDF Page 10
    {'prop': 'north_sea', 'acc_type': 'full_apartment', 'guest': 'international', 'stay': 'weekly', 'min_nights': 7, 'price': '171.43', 'weekly': '1200', 'breakfast': False, 'fullboard': False},
    
    # MSAMBWENI - PDF Page 16
    {'prop': 'msambweni', 'acc_type': 'full_apartment', 'guest': 'international', 'stay': 'short_term', 'min_nights': 2, 'price': '450', 'weekly': None, 'breakfast': True, 'fullboard': True},
    {'prop': 'msambweni', 'acc_type': 'master_bedroom', 'guest': 'international', 'stay': 'short_term', 'min_nights': 2, 'price': '300', 'weekly': None, 'breakfast': True, 'fullboard': True},
    {'prop': 'msambweni', 'acc_type': 'full_apartment', 'guest': 'local', 'stay': 'short_term', 'min_nights': 2, 'price': '350', 'weekly': None, 'breakfast': True, 'fullboard': True},
    {'prop': 'msambweni', 'acc_type': 'master_bedroom', 'guest': 'local', 'stay': 'short_term', 'min_nights': 2, 'price': '250', 'weekly': None, 'breakfast': True, 'fullboard': True},
    
    # MARBLE INN - PDF Page 17-18
    {'prop': 'marble', 'acc_type': 'single_bedroom', 'guest': 'international', 'stay': 'short_term', 'min_nights': 2, 'price': '100', 'weekly': '500', 'breakfast': True, 'fullboard': False},  # 1 person
    {'prop': 'marble', 'acc_type': 'master_bedroom', 'guest': 'international', 'stay': 'short_term', 'min_nights': 2, 'price': '120', 'weekly': '600', 'breakfast': True, 'fullboard': False},  # 2 people
    {'prop': 'marble', 'acc_type': 'full_apartment', 'guest': 'international', 'stay': 'short_term', 'min_nights': 2, 'price': '200', 'weekly': '1000', 'breakfast': True, 'fullboard': False},
    
    # HUB - PDF Page 19 (accommodation, not co-working)
    {'prop': 'hub', 'acc_type': 'single_bedroom', 'guest': 'international', 'stay': 'short_term', 'min_nights': 4, 'price': '75', 'weekly': None, 'breakfast': False, 'fullboard': False},
    {'prop': 'hub', 'acc_type': 'single_bedroom', 'guest': 'international', 'stay': 'long_term', 'min_nights': 30, 'price': '33.33', 'weekly': None, 'breakfast': False, 'fullboard': False},  # €1000/month = €33.33/night
]

for p in pricing_data:
    price_obj, created = PropertyPricing.objects.get_or_create(
        property=props[p['prop']],
        accommodation_type=p['acc_type'],
        guest_type=p['guest'],
        stay_type=p['stay'],
        defaults={
            'price_per_night': Decimal(p['price']),
            'weekly_price': Decimal(p['weekly']) if p['weekly'] else None,
            'min_nights': p['min_nights'],
            'max_nights': p.get('max_nights'),
            'includes_breakfast': p['breakfast'],
            'includes_fullboard': p['fullboard']
        }
    )
    stay_label = f"{p['stay']} ({p['min_nights']}+ nights)" if p.get('min_nights') else p['stay']
    print(f"{'Created' if created else 'Exists'}: {props[p['prop']].name} - {p['acc_type']} - {stay_label}")

# Create Company Info
print("\n=== Creating Company Info ===")
print(f"{'Created' if created else 'Exists'}: Company Info")

# Create Property Features
print("\n=== Creating Property Features ===")
features_data = [
    {'prop': 'brussels', 'type': 'outdoor', 'name': 'Park View', 'desc': 'Stunning views of local park'},
    {'prop': 'brussels', 'type': 'indoor', 'name': 'Smart TV', 'desc': '55-inch smart TV with streaming services'},
    {'prop': 'brussels', 'type': 'indoor', 'name': 'Dedicated Workspace', 'desc': 'Professional workspace with ergonomic chair'},
    {'prop': 'north_sea', 'type': 'outdoor', 'name': 'Beachfront Terrace', 'desc': '30m² terrace with ocean views'},
    {'prop': 'north_sea', 'type': 'outdoor', 'name': 'Beach Access', 'desc': 'Direct private beach access'},
    {'prop': 'msambweni', 'type': 'outdoor', 'name': 'Infinity Pool', 'desc': 'Ocean-view infinity pool'},
    {'prop': 'msambweni', 'type': 'outdoor', 'name': 'Private Beach', 'desc': '200m of private beachfront'},
    {'prop': 'marble', 'type': 'indoor', 'name': 'Rooftop Terrace', 'desc': 'Shared rooftop terrace with city views'},
    {'prop': 'marble', 'type': 'indoor', 'name': 'Breakfast Included', 'desc': 'Daily breakfast included'},
    {'prop': 'hub', 'type': 'indoor', 'name': 'Co-working Space', 'desc': 'Modern co-working facilities'},
    {'prop': 'hub', 'type': 'indoor', 'name': 'Meeting Rooms', 'desc': 'Bookable meeting rooms'},
    {'prop': 'hub', 'type': 'indoor', 'name': 'Event Space', 'desc': 'Community event space'},
]

for feat in features_data:
    obj, created = PropertyFeature.objects.get_or_create(
        property=props[feat['prop']],
        name=feat['name'],
        defaults={
            'feature_type': feat['type'],
            'description': feat['desc']
        }
    )
    print(f"{'Created' if created else 'Exists'}: {feat['name']} - {props[feat['prop']].name}")

# Create Property Contacts
print("\n=== Creating Property Contacts ===")
contacts_data = [
    {'prop': 'brussels', 'name': 'Marie Verbreyt', 'role': 'Property Manager', 'email': 'requests@techbedkifaru.be', 'phone': '+32 472 123 456', 'whatsapp': '+32 472 123 456'},
    {'prop': 'north_sea', 'name': 'Marie Verbreyt', 'role': 'Property Manager', 'email': 'requests@techbedkifaru.be', 'phone': '+32 472 123 456', 'whatsapp': '+32 472 123 456'},
    {'prop': 'msambweni', 'name': 'Faith', 'role': 'Butler & Concierge', 'email': 'msambweni@kifaruimpact.com', 'phone': '+254 700 000 001', 'whatsapp': '+254 700 000 001'},
    {'prop': 'marble', 'name': 'Lydia', 'role': 'Host', 'email': 'marble@kifaruimpact.com', 'phone': '+254 700 000 002', 'whatsapp': '+254 700 000 002'},
    {'prop': 'hub', 'name': 'Anjelina Smith', 'role': 'Community Manager', 'email': 'anjelina@closethegap.co.ke', 'phone': '+254 700 000 003', 'whatsapp': '+254 700 000 003'},
]

for contact in contacts_data:
    obj, created = PropertyContact.objects.get_or_create(
        property=props[contact['prop']],
        email=contact['email'],
        defaults={
            'name': contact['name'],
            'role': contact['role'],
            'phone': contact['phone'],
            'whatsapp': contact['whatsapp'],
        }
    )
    print(f"{'Created' if created else 'Exists'}: {contact['name']} - {props[contact['prop']].name}")

# Create Property Networks (related properties)
print("\n=== Creating Property Networks ===")
networks_data = [
    {'from': 'brussels', 'to': 'north_sea', 'time': 120, 'transport': True, 'desc': 'Direct train connection available'},
    {'from': 'msambweni', 'to': 'marble', 'time': 90, 'transport': True, 'desc': 'Shuttle service available'},
    {'from': 'marble', 'to': 'hub', 'time': 15, 'transport': False, 'desc': 'Walking distance in same compound'},
]

for net in networks_data:
    obj, created = PropertyNetwork.objects.get_or_create(
        property=props[net['from']],
        related_property=props[net['to']],
        defaults={
            'travel_time_minutes': net['time'],
            'transport_available': net['transport'],
            'description': net['desc']
        }
    )
    print(f"{'Created' if created else 'Exists'}: {props[net['from']].name} → {props[net['to']].name}")

print("\n✅ Data population completed!")
print(f"\nCreated:")
print(f"  - {len(properties_data)} properties")
print(f"  - {len(pricing_data)} pricing options")
print(f"  - {len(features_data)} property features")
print(f"  - {len(contacts_data)} property contacts")
print(f"  - {len(networks_data)} property networks")
print(f"\n🎉 All models populated with sample data!")
