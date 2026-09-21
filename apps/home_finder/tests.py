from io import StringIO
from django.core.management import call_command
from django.test import TestCase

from apps.home_finder.models import Amenity, Property, PropertyMedia, PropertyInterest
from apps.tenant.models import SavedProperty, ViewingRequest, PropertyAlert


class PropertySeederTest(TestCase):
    def test_seed_properties_command(self):
        out = StringIO()
        call_command("seed_properties", stdout=out)
        output = out.getvalue()

        self.assertIn("Property App Database Seeding Complete!", output)
        self.assertGreater(Amenity.objects.count(), 0)
        self.assertGreater(Property.objects.count(), 0)
        self.assertGreater(PropertyMedia.objects.count(), 0)
        self.assertGreater(PropertyInterest.objects.count(), 0)
        self.assertGreater(SavedProperty.objects.count(), 0)
        self.assertGreater(ViewingRequest.objects.count(), 0)

    def test_seed_properties_no_tenants_option(self):
        out = StringIO()
        call_command("seed_properties", "--clear", "--no-tenants", stdout=out)

        self.assertGreater(Property.objects.count(), 0)
        self.assertEqual(SavedProperty.objects.count(), 0)
        self.assertEqual(ViewingRequest.objects.count(), 0)
        self.assertEqual(PropertyAlert.objects.count(), 0)

    def test_seed_properties_clear_option(self):
        out = StringIO()
        call_command("seed_properties", stdout=out)
        initial_count = Property.objects.count()
        self.assertGreater(initial_count, 0)

        out_clear = StringIO()
        call_command("seed_properties", "--clear", stdout=out_clear)
        self.assertEqual(Property.objects.count(), initial_count)
