"""
Database seeder for Property models and related property objects.

Creates:
  * Amenities (rich collection of common Ghanaian rental property amenities)
  * Demo Landlord Users & Profiles
  * Demo Tenant Users & Profiles
  * Landlord Documents (verified national ID / proof of ownership for document verification filters)
  * Property listings across diverse Ghanaian locations (Accra, Kumasi, Takoradi, etc.)
  * Property Media (images/documents)
  * Property Interests
  * Saved Properties (Tenant)
  * Property Views (Tenant)
  * Viewing Requests (Tenant)
  * Property Alerts (Tenant)

Idempotent: running it again updates existing rows in place or skips duplicates.
Use --clear to wipe existing properties & property-related data first.

Usage:
    python manage.py seed_properties
    python manage.py seed_properties --clear
    python manage.py seed_properties --no-tenants
"""

import os
import random
import logging
from datetime import date, timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.account.models import User, LandlordProfile, TenantProfile
from apps.common.cache import (
    invalidate_property_cache,
    invalidate_amenities_cache,
    invalidate_locations_cache,
)
from apps.home_finder.models import (
    Amenity,
    Property,
    PropertyMedia,
    PropertyInterest,
    LandlordDocument,
)
from apps.locations.models import Region, District, Town, Area
from apps.tenant.models import (
    SavedProperty,
    PropertyView,
    PropertyAlert,
    ViewingRequest,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Amenities Catalogue
# -----------------------------------------------------------------------------
AMENITIES_CATALOG = [
    {"name": "24/7 Security", "description": "Gated security guard post and round-the-clock security personnel."},
    {"name": "Standby Generator", "description": "Automatic backup power generator during power outages (dumsor)."},
    {"name": "Water Tank / PolyTank", "description": "Overhead water storage poly-tank with automated pump."},
    {"name": "Air Conditioning", "description": "Fitted split AC units in main living areas and bedrooms."},
    {"name": "Fitted Kitchen", "description": "Modern kitchen cabinets, countertop, and sink installation."},
    {"name": "Parking Space", "description": "Dedicated paved parking space inside compound."},
    {"name": "Balcony & Terrace", "description": "Private balcony or terrace with scenic neighborhood views."},
    {"name": "Swimming Pool", "description": "Access to clean swimming pool on property grounds."},
    {"name": "Gated Compound", "description": "Fully walled compound with electric fence and gated entry."},
    {"name": "Washing Machine", "description": "Laundry hookups and dedicated washing machine area."},
    {"name": "Self Electricity Meter", "description": "Independent prepaid ECG electricity meter for the unit."},
    {"name": "High-Speed WiFi / Fiber", "description": "Pre-wired high-speed broadband fiber internet connection."},
    {"name": "CCTV Surveillance", "description": "Security cameras covering common areas and entrance gates."},
    {"name": "Solar Power System", "description": "Solar panels and inverter battery backup system."},
    {"name": "Tarred Access Road", "description": "Easily accessible via smooth tarred road network."},
    {"name": "Built-in Wardrobes", "description": "Spacious floor-to-ceiling wardrobes in bedrooms."},
    {"name": "Ensuite Bedrooms", "description": "Bedrooms equipped with private attached bathrooms."},
    {"name": "Water Heater", "description": "Instant hot water shower systems installed in bathrooms."},
]


# -----------------------------------------------------------------------------
# Demo Users
# -----------------------------------------------------------------------------
DEMO_LANDLORDS = [
    {
        "email": "kwame.mensah@vacanthommie.com",
        "full_name": "Kwame Mensah",
        "phone_number": "+233244111222",
        "company_name": "Gold Coast Properties",
    },
    {
        "email": "abena.appiah@vacanthommie.com",
        "full_name": "Abena Appiah",
        "phone_number": "+233244222333",
        "company_name": "Appiah Real Estate & Rentals",
    },
    {
        "email": "kofi.addo@vacanthommie.com",
        "full_name": "Kofi Addo",
        "phone_number": "+233244333444",
        "company_name": "Kofi Addo Holdings",
    },
    {
        "email": "yaas.owusu@vacanthommie.com",
        "full_name": "Yaa Owusu",
        "phone_number": "+233244444555",
        "company_name": "Owusu Premium Rentals",
    },
]

DEMO_TENANTS = [
    {
        "email": "kweku.baah@vacanthommie.com",
        "full_name": "Kweku Baah",
        "phone_number": "+233277111000",
        "employer_name": "MTN Ghana",
    },
    {
        "email": "adwoa.serwaa@vacanthommie.com",
        "full_name": "Adwoa Serwaa",
        "phone_number": "+233277222000",
        "employer_name": "Ecobank Ghana",
    },
    {
        "email": "fiifi.dankwa@vacanthommie.com",
        "full_name": "Fiifi Dankwa",
        "phone_number": "+233277333000",
        "employer_name": "Vodafone Ghana",
    },
]


# -----------------------------------------------------------------------------
# Properties Specifications Catalogue
# -----------------------------------------------------------------------------
PROPERTY_SPECS = [
    {
        "title": "Modern 2-Bedroom Apartment in East Legon",
        "description": (
            "Exquisite 2-bedroom apartment located in the serene enclave of East Legon. "
            "Features spacious en-suite bedrooms, a fully fitted modern kitchen with granite tops, "
            "private balcony, standby generator, and 24/7 security guard. Perfect for professionals or small families."
        ),
        "price": "3500.00",
        "payment_period": Property.PaymentPeriod.MONTHLY,
        "room_type": Property.RoomType.APARTMENT,
        "verification_status": Property.VerificationStatus.VERIFIED,
        "publication_status": Property.PublicationStatus.PUBLISHED,
        "region_name": "Greater Accra",
        "district_name": "Ayawaso West Municipal",
        "town_name": "East Legon",
        "area_name": "East Legon Central",
        "bedrooms": 2,
        "bathrooms": 2,
        "toilets": 3,
        "parking_spaces": 2,
        "floor_area": 120.50,
        "is_furnished": True,
        "is_available": True,
        "latitude": 5.6358,
        "longitude": -0.1583,
        "amenity_names": ["24/7 Security", "Standby Generator", "Air Conditioning", "Fitted Kitchen", "Parking Space", "Balcony & Terrace", "Self Electricity Meter"],
        "cover_name": "apartment.jpg",
        "landlord_index": 0,
    },
    {
        "title": "Executive 3-Bedroom House with Pool in Cantonments",
        "description": (
            "Luxury 3-bedroom detached house in prime Cantonments. Comes with a private swimming pool, "
            "large paved compound, solar power backup, electric fencing, and high-end security. "
            "Ideal for diplomats, corporate executives, or expats."
        ),
        "price": "12000.00",
        "payment_period": Property.PaymentPeriod.MONTHLY,
        "room_type": Property.RoomType.APARTMENT,
        "verification_status": Property.VerificationStatus.VERIFIED,
        "publication_status": Property.PublicationStatus.PUBLISHED,
        "region_name": "Greater Accra",
        "district_name": "Accra Metropolitan",
        "town_name": "Cantonments",
        "area_name": "Cantonments Central",
        "bedrooms": 3,
        "bathrooms": 3,
        "toilets": 4,
        "parking_spaces": 3,
        "floor_area": 280.00,
        "is_furnished": True,
        "is_available": True,
        "latitude": 5.5786,
        "longitude": -0.1764,
        "amenity_names": ["24/7 Security", "Standby Generator", "Swimming Pool", "Solar Power System", "Gated Compound", "Ensuite Bedrooms"],
        "cover_name": "1.webp",
        "landlord_index": 1,
    },
    {
        "title": "Cozy Chamber & Hall Self-Contained in Dansoman",
        "description": (
            "Neat and newly renovated chamber and hall self-contained apartment in Dansoman Control. "
            "Includes personal ECG prepaid meter, constant flow water supply with poly-tank, tiled floors, "
            "and secure walled compound."
        ),
        "price": "850.00",
        "payment_period": Property.PaymentPeriod.MONTHLY,
        "room_type": Property.RoomType.CHAMBER_AND_HALL,
        "verification_status": Property.VerificationStatus.VERIFIED,
        "publication_status": Property.PublicationStatus.PUBLISHED,
        "region_name": "Greater Accra",
        "district_name": "Ablekuma West Municipal",
        "town_name": "Dansoman",
        "area_name": "Control",
        "bedrooms": 1,
        "bathrooms": 1,
        "toilets": 1,
        "parking_spaces": 1,
        "floor_area": 45.00,
        "is_furnished": False,
        "is_available": True,
        "latitude": 5.5492,
        "longitude": -0.2561,
        "amenity_names": ["Water Tank / PolyTank", "Self Electricity Meter", "Tarred Access Road"],
        "cover_name": "2.jpeg",
        "landlord_index": 2,
    },
    {
        "title": "Self-Contained Studio Unit near KNUST, Kumasi",
        "description": (
            "Convenient self-contained studio apartment located at Ayeduase, close to KNUST campus gate. "
            "Features private bathroom, kitchenette, study desk area, high-speed WiFi ready, and water heater. "
            "Great for university students or young professionals."
        ),
        "price": "600.00",
        "payment_period": Property.PaymentPeriod.MONTHLY,
        "room_type": Property.RoomType.SELF_CONTAINED,
        "verification_status": Property.VerificationStatus.VERIFIED,
        "publication_status": Property.PublicationStatus.PUBLISHED,
        "region_name": "Ashanti",
        "district_name": "Oforikrom Municipal",
        "town_name": "Oforikrom",
        "area_name": "Ayeduase",
        "bedrooms": 1,
        "bathrooms": 1,
        "toilets": 1,
        "parking_spaces": 1,
        "floor_area": 35.00,
        "is_furnished": False,
        "is_available": True,
        "latitude": 6.6731,
        "longitude": -1.5645,
        "amenity_names": ["Water Tank / PolyTank", "High-Speed WiFi / Fiber", "Water Heater"],
        "cover_name": "apartment.jpg",
        "landlord_index": 3,
    },
    {
        "title": "Spacious 4-Bedroom Villa in Ahodwo, Kumasi",
        "description": (
            "Magnificent 4-bedroom villa with boy's quarters in prime Ahodwo, Kumasi. "
            "Boasts manicured lawn gardens, double garage, solar power backup system, CCTV cameras, "
            "and automatic remote control gate."
        ),
        "price": "8000.00",
        "payment_period": Property.PaymentPeriod.MONTHLY,
        "room_type": Property.RoomType.APARTMENT,
        "verification_status": Property.VerificationStatus.VERIFIED,
        "publication_status": Property.PublicationStatus.PUBLISHED,
        "region_name": "Ashanti",
        "district_name": "Kumasi Metropolitan",
        "town_name": "Nhyiaeso",
        "area_name": "Ahodwo",
        "bedrooms": 4,
        "bathrooms": 4,
        "toilets": 5,
        "parking_spaces": 4,
        "floor_area": 350.00,
        "is_furnished": True,
        "is_available": True,
        "latitude": 6.6712,
        "longitude": -1.6258,
        "amenity_names": ["24/7 Security", "Standby Generator", "Solar Power System", "CCTV Surveillance", "Gated Compound", "Built-in Wardrobes"],
        "cover_name": "1.webp",
        "landlord_index": 0,
    },
    {
        "title": "Furnished Guest House Suite in Osu, Accra",
        "description": (
            "Charming short-stay furnished guest house suite in vibrant Osu near Oxford Street. "
            "Daily housekeeping, complimentary high-speed WiFi, air conditioning, microwave, "
            "and 24-hour concierge service included."
        ),
        "price": "450.00",
        "payment_period": Property.PaymentPeriod.DAILY,
        "room_type": Property.RoomType.GUEST_HOUSE,
        "verification_status": Property.VerificationStatus.VERIFIED,
        "publication_status": Property.PublicationStatus.PUBLISHED,
        "region_name": "Greater Accra",
        "district_name": "Korle Klottey Municipal",
        "town_name": "Osu",
        "area_name": "Oxford Street",
        "bedrooms": 1,
        "bathrooms": 1,
        "toilets": 1,
        "parking_spaces": 1,
        "floor_area": 40.00,
        "is_furnished": True,
        "is_available": True,
        "latitude": 5.5562,
        "longitude": -0.1822,
        "amenity_names": ["Air Conditioning", "High-Speed WiFi / Fiber", "24/7 Security", "Standby Generator"],
        "cover_name": "2.jpeg",
        "landlord_index": 1,
    },
    {
        "title": "Beachfront 2-Bedroom Flat in Takoradi",
        "description": (
            "Beautiful beachfront 2-bedroom apartment overlooking the ocean in Takoradi. "
            "Features ocean view balcony, modern kitchen appliances, AC in all rooms, and steady water supply."
        ),
        "price": "2800.00",
        "payment_period": Property.PaymentPeriod.MONTHLY,
        "room_type": Property.RoomType.APARTMENT,
        "verification_status": Property.VerificationStatus.VERIFIED,
        "publication_status": Property.PublicationStatus.PUBLISHED,
        "region_name": "Western",
        "district_name": "Sekondi Takoradi Metropolitan",
        "town_name": "Takoradi",
        "area_name": "Beach Road",
        "bedrooms": 2,
        "bathrooms": 2,
        "toilets": 2,
        "parking_spaces": 2,
        "floor_area": 110.00,
        "is_furnished": True,
        "is_available": True,
        "latitude": 4.8872,
        "longitude": -1.7589,
        "amenity_names": ["Balcony & Terrace", "Air Conditioning", "Fitted Kitchen", "Water Tank / PolyTank", "Tarred Access Road"],
        "cover_name": "apartment.jpg",
        "landlord_index": 2,
    },
    {
        "title": "Modern 3-Bedroom Townhouse in Tema Community 25",
        "description": (
            "Gated community 3-bedroom townhouse in Tema Community 25. "
            "Features 24/7 security patrol, children's playground, swimming pool, paved driveways, "
            "and fitted kitchen."
        ),
        "price": "4200.00",
        "payment_period": Property.PaymentPeriod.MONTHLY,
        "room_type": Property.RoomType.APARTMENT,
        "verification_status": Property.VerificationStatus.VERIFIED,
        "publication_status": Property.PublicationStatus.PUBLISHED,
        "region_name": "Greater Accra",
        "district_name": "Tema Metropolitan",
        "town_name": "Tema Community 25",
        "area_name": "Devtraco Courts",
        "bedrooms": 3,
        "bathrooms": 3,
        "toilets": 4,
        "parking_spaces": 2,
        "floor_area": 195.00,
        "is_furnished": False,
        "is_available": True,
        "latitude": 5.7142,
        "longitude": 0.0125,
        "amenity_names": ["24/7 Security", "Swimming Pool", "Gated Compound", "Parking Space", "Self Electricity Meter"],
        "cover_name": "1.webp",
        "landlord_index": 3,
    },
    {
        "title": "Affordable 1-Bedroom Apartment in Spintex",
        "description": (
            "Newly built 1-bedroom apartment off Spintex Road near Coastal Estate. "
            "Self ECG meter, overhead PolyTank water supply, tarred road connection, and spacious living area."
        ),
        "price": "1400.00",
        "payment_period": Property.PaymentPeriod.MONTHLY,
        "room_type": Property.RoomType.APARTMENT,
        "verification_status": Property.VerificationStatus.VERIFIED,
        "publication_status": Property.PublicationStatus.PUBLISHED,
        "region_name": "Greater Accra",
        "district_name": "Ledzokuku Municipal",
        "town_name": "Teshie",
        "area_name": "Bush Road",
        "bedrooms": 1,
        "bathrooms": 1,
        "toilets": 1,
        "parking_spaces": 1,
        "floor_area": 60.00,
        "is_furnished": False,
        "is_available": True,
        "latitude": 5.6120,
        "longitude": -0.1088,
        "amenity_names": ["Water Tank / PolyTank", "Self Electricity Meter", "Tarred Access Road"],
        "cover_name": "2.jpeg",
        "landlord_index": 0,
    },
    {
        "title": "Luxury Penthouse in Ridge, Accra (Pending Review)",
        "description": (
            "Unmatched penthouse apartment with panoramic skyline views over Ridge and West Ridge. "
            "Features private elevator access, rooftop deck, floor-to-ceiling glass windows, and Smart Home controls."
        ),
        "price": "18000.00",
        "payment_period": Property.PaymentPeriod.MONTHLY,
        "room_type": Property.RoomType.APARTMENT,
        "verification_status": Property.VerificationStatus.PENDING,
        "publication_status": Property.PublicationStatus.DRAFT,
        "region_name": "Greater Accra",
        "district_name": "Korle Klottey Municipal",
        "town_name": "Ridge",
        "area_name": "North Ridge",
        "bedrooms": 3,
        "bathrooms": 3,
        "toilets": 4,
        "parking_spaces": 3,
        "floor_area": 320.00,
        "is_furnished": True,
        "is_available": True,
        "latitude": 5.5688,
        "longitude": -0.1989,
        "amenity_names": ["24/7 Security", "Standby Generator", "Swimming Pool", "CCTV Surveillance", "Balcony & Terrace"],
        "cover_name": "apartment.jpg",
        "landlord_index": 1,
    },
]


class Command(BaseCommand):
    help = "Seed database with Property models, amenities, landlord documents, and tenant interactions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear all existing property data, amenities, landlord documents, and tenant property interactions.",
        )
        parser.add_argument(
            "--no-tenants",
            action="store_true",
            help="Skip creating demo tenant interactions (saved properties, viewing requests, property alerts).",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting Property models database seeding..."))

        if options.get("clear"):
            self._clear_existing()

        # Ensure location data exists first
        self._ensure_locations_exist()

        with transaction.atomic():
            amenities_by_name = self._seed_amenities()
            landlords = self._seed_demo_landlords()
            tenants = self._seed_demo_tenants()
            self._seed_landlord_documents(landlords)
            properties = self._seed_properties(landlords, amenities_by_name)
            self._seed_property_media(properties)

            if not options.get("no_tenants") and tenants and properties:
                self._seed_tenant_interactions(tenants, properties)

        # Invalidate caches
        invalidate_property_cache()
        invalidate_amenities_cache()
        invalidate_locations_cache()

        self._print_summary()

    def _clear_existing(self):
        self.stdout.write(self.style.WARNING("Clearing existing Property and related data..."))
        ViewingRequest.objects.all().delete()
        PropertyAlert.objects.all().delete()
        PropertyView.objects.all().delete()
        SavedProperty.objects.all().delete()
        PropertyInterest.objects.all().delete()
        PropertyMedia.objects.all().delete()
        LandlordDocument.objects.all().delete()
        Property.objects.all().delete()
        Amenity.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("  Cleared existing property data."))

    def _ensure_locations_exist(self):
        if Region.objects.count() == 0 or District.objects.count() == 0:
            self.stdout.write("No location data found in DB. Seeding Ghana locations first...")
            call_command("seed_ghana_locations")

    def _seed_amenities(self) -> dict:
        self.stdout.write("Seeding Amenities...")
        amenities_by_name = {}
        for spec in AMENITIES_CATALOG:
            amenity, created = Amenity.objects.update_or_create(
                name=spec["name"],
                defaults={"description": spec["description"]},
            )
            amenities_by_name[amenity.name] = amenity
            verb = "Created" if created else "Updated"
            self.stdout.write(f"  - {verb} amenity: {amenity.name}")
        return amenities_by_name

    def _seed_demo_landlords(self) -> list[User]:
        self.stdout.write("Seeding Demo Landlord Users...")
        landlords = []
        for spec in DEMO_LANDLORDS:
            user, created = User.objects.get_or_create(
                email=spec["email"],
                defaults={
                    "full_name": spec["full_name"],
                    "phone_number": spec["phone_number"],
                    "role": User.Role.LANDLORD,
                    "is_email_verified": True,
                },
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])

            LandlordProfile.objects.get_or_create(
                user=user,
                defaults={"company_name": spec["company_name"]},
            )
            landlords.append(user)
            verb = "Created" if created else "Found"
            self.stdout.write(f"  - {verb} landlord: {user.full_name} ({user.email})")
        return landlords

    def _seed_demo_tenants(self) -> list[User]:
        self.stdout.write("Seeding Demo Tenant Users...")
        tenants = []
        for spec in DEMO_TENANTS:
            user, created = User.objects.get_or_create(
                email=spec["email"],
                defaults={
                    "full_name": spec["full_name"],
                    "phone_number": spec["phone_number"],
                    "role": User.Role.TENANT,
                    "is_email_verified": True,
                },
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])

            TenantProfile.objects.get_or_create(
                user=user,
                defaults={"employer_name": spec["employer_name"]},
            )
            tenants.append(user)
            verb = "Created" if created else "Found"
            self.stdout.write(f"  - {verb} tenant: {user.full_name} ({user.email})")
        return tenants

    def _seed_landlord_documents(self, landlords: list[User]):
        """
        Creates verified National ID and Property Ownership documents for landlords
        so that their published properties pass selector verification filters.
        """
        self.stdout.write("Seeding Landlord Verification Documents...")
        doc_dir = os.path.join(settings.MEDIA_ROOT, "landlords", "documents")
        os.makedirs(doc_dir, exist_ok=True)
        dummy_doc_path = os.path.join(doc_dir, "sample_id.pdf")
        if not os.path.exists(dummy_doc_path):
            with open(dummy_doc_path, "wb") as f:
                f.write(b"%PDF-1.4 sample verification document for seeder")

        rel_doc_path = "landlords/documents/sample_id.pdf"

        for landlord in landlords:
            doc, created = LandlordDocument.objects.get_or_create(
                landlord=landlord,
                document_type=LandlordDocument.DocumentType.NATIONAL_ID,
                defaults={
                    "file": rel_doc_path,
                    "verification_status": LandlordDocument.VerificationStatus.VERIFIED,
                },
            )
            if not created and doc.verification_status != LandlordDocument.VerificationStatus.VERIFIED:
                doc.verification_status = LandlordDocument.VerificationStatus.VERIFIED
                doc.save(update_fields=["verification_status"])

            verb = "Created" if created else "Verified"
            self.stdout.write(f"  - {verb} National ID document for {landlord.full_name}")

    def _ensure_cover_image(self, filename: str) -> str:
        """
        Ensures a dummy cover image file exists in media/properties/covers/
        and returns the relative upload path.
        """
        covers_dir = os.path.join(settings.MEDIA_ROOT, "properties", "covers")
        os.makedirs(covers_dir, exist_ok=True)
        target_path = os.path.join(covers_dir, filename)

        if not os.path.exists(target_path):
            minimal_image_bytes = (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
                b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
                b"\x08\xa0\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
                b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \x1c\x1c(7),01444\x1f'9=82<.342"
                b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4"
                b"\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00"
                b"\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
                b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
            )
            with open(target_path, "wb") as f:
                f.write(minimal_image_bytes)

        return f"properties/covers/{filename}"

    def _seed_properties(self, landlords: list[User], amenities_by_name: dict) -> list[Property]:
        self.stdout.write("Seeding Properties...")
        seeded_properties = []

        for spec in PROPERTY_SPECS:
            landlord = landlords[spec["landlord_index"] % len(landlords)]

            # Resolve location objects flexibly
            region = Region.objects.filter(name=spec["region_name"]).first()
            if not region:
                region = Region.objects.first()

            district = District.objects.filter(region=region, name=spec["district_name"]).first()
            if not district and region:
                district = District.objects.filter(region=region).first()

            town = Town.objects.filter(name=spec["town_name"]).first()
            if not town and district:
                town = Town.objects.filter(district=district).first()

            area = Area.objects.filter(name=spec["area_name"]).first()
            if not area and town:
                area = Area.objects.filter(town=town).first()

            if not (region and district and town and area):
                self.stdout.write(self.style.WARNING(f"  Skipping '{spec['title']}': location resolution failed"))
                continue

            # Update region/district to match actual town/area ancestry if needed
            if town.district:
                district = town.district
                if district.region:
                    region = district.region

            cover_rel_path = self._ensure_cover_image(spec["cover_name"])

            defaults = {
                "description": spec["description"],
                "cover_image": cover_rel_path,
                "price": spec["price"],
                "payment_period": spec["payment_period"],
                "room_type": spec["room_type"],
                "verification_status": spec["verification_status"],
                "publication_status": spec["publication_status"],
                "region": region,
                "district": district,
                "town": town,
                "area": area,
                "bedrooms": spec["bedrooms"],
                "bathrooms": spec["bathrooms"],
                "toilets": spec["toilets"],
                "parking_spaces": spec["parking_spaces"],
                "floor_area": spec["floor_area"],
                "is_furnished": spec["is_furnished"],
                "is_available": spec["is_available"],
                "latitude": spec["latitude"],
                "longitude": spec["longitude"],
                "available_from": date.today(),
            }

            prop, created = Property.objects.update_or_create(
                landlord=landlord,
                title=spec["title"],
                defaults=defaults,
            )

            # Assign amenities
            prop_amenities = [
                amenities_by_name[name] for name in spec["amenity_names"] if name in amenities_by_name
            ]
            prop.amenities.set(prop_amenities)

            seeded_properties.append(prop)
            verb = "Created" if created else "Updated"
            self.stdout.write(f"  - {verb} property: {prop.title} [GHS {prop.price}/{prop.payment_period}]")

        return seeded_properties

    def _seed_property_media(self, properties: list[Property]):
        self.stdout.write("Seeding Property Media...")
        media_dir = os.path.join(settings.MEDIA_ROOT, "properties", "media")
        os.makedirs(media_dir, exist_ok=True)
        dummy_media_path = os.path.join(media_dir, "sample_photo.jpg")

        if not os.path.exists(dummy_media_path):
            minimal_jpg = (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
                b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
                b"\x08\xa0\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
                b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \x1c\x1c(7),01444\x1f'9=82<.342"
                b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4"
                b"\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00"
                b"\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
                b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
            )
            with open(dummy_media_path, "wb") as f:
                f.write(minimal_jpg)

        rel_media_path = "properties/media/sample_photo.jpg"

        for prop in properties:
            captions = [
                "Living area view",
                "Fitted kitchen & pantry",
                "Master bedroom ensuite",
                "Exterior compound view",
            ]
            for order, caption in enumerate(captions, start=1):
                PropertyMedia.objects.get_or_create(
                    property=prop,
                    order=order,
                    defaults={
                        "file": rel_media_path,
                        "media_type": PropertyMedia.MediaType.IMAGE,
                        "caption": caption,
                        "is_public": True,
                        "is_processed": True,
                    },
                )
        self.stdout.write(f"  - Attached media images to {len(properties)} properties.")

    def _seed_tenant_interactions(self, tenants: list[User], properties: list[Property]):
        self.stdout.write("Seeding Tenant Interactions (Interests, Saved, Views, Requests, Alerts)...")
        published_props = [p for p in properties if p.publication_status == Property.PublicationStatus.PUBLISHED]
        if not published_props:
            published_props = properties

        for tenant in tenants:
            # Property Interest
            sample_props = random.sample(published_props, min(3, len(published_props)))
            for prop in sample_props:
                PropertyInterest.objects.get_or_create(property=prop, tenant=tenant)
                SavedProperty.objects.get_or_create(property=prop, tenant=tenant)
                PropertyView.objects.get_or_create(property=prop, tenant=tenant)

            # Viewing Requests
            req_prop = random.choice(published_props)
            ViewingRequest.objects.get_or_create(
                property=req_prop,
                tenant=tenant,
                preferred_date=date.today() + timedelta(days=3),
                defaults={
                    "preferred_time": "14:00:00",
                    "notes": "Interested in viewing this weekend afternoon.",
                    "status": ViewingRequest.Status.PENDING,
                },
            )

            # Property Alert
            if published_props:
                alert_prop = published_props[0]
                PropertyAlert.objects.get_or_create(
                    tenant=tenant,
                    region=alert_prop.region,
                    district=alert_prop.district,
                    area=alert_prop.area,
                    room_type=alert_prop.room_type,
                    defaults={
                        "min_price": "500.00",
                        "max_price": "5000.00",
                        "is_active": True,
                    },
                )

        self.stdout.write(self.style.SUCCESS("  - Tenant interactions seeded successfully."))

    def _print_summary(self):
        total_amenities = Amenity.objects.count()
        total_properties = Property.objects.count()
        published_properties = Property.objects.filter(
            publication_status=Property.PublicationStatus.PUBLISHED,
            verification_status=Property.VerificationStatus.VERIFIED,
            is_available=True,
        ).count()
        total_media = PropertyMedia.objects.count()
        total_interests = PropertyInterest.objects.count()
        total_saved = SavedProperty.objects.count()
        total_viewings = ViewingRequest.objects.count()

        self.stdout.write(self.style.SUCCESS(
            "\n============================================================\n"
            "Property App Database Seeding Complete!\n"
            "============================================================\n"
            f"  Amenities:            {total_amenities} total\n"
            f"  Properties:           {total_properties} total ({published_properties} published & verified)\n"
            f"  Property Media:       {total_media} total\n"
            f"  Property Interests:   {total_interests} total\n"
            f"  Saved Properties:     {total_saved} total\n"
            f"  Viewing Requests:     {total_viewings} total\n"
            "============================================================"
        ))
