from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.accounts.identity import normalize_email, normalize_phone


class NormalizeEmailTests(SimpleTestCase):
    def test_lowercases_the_whole_address(self):
        self.assertEqual(normalize_email("Ada.Okeke@Example.COM"), "ada.okeke@example.com")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(normalize_email("  ada@example.com \n"), "ada@example.com")

    def test_applies_unicode_compatibility_normalisation(self):
        # Fullwidth characters render identically to ASCII in most fonts, so without
        # NFKC two visually identical addresses would be two separate accounts.
        self.assertEqual(normalize_email("ａda@example.com"), "ada@example.com")  # noqa: RUF001


class NormalizePhoneTests(SimpleTestCase):
    def test_converts_a_local_nigerian_number_to_e164(self):
        self.assertEqual(normalize_phone("08031234567"), "+2348031234567")

    def test_accepts_spaced_and_punctuated_input(self):
        self.assertEqual(normalize_phone("0803 123 4567"), "+2348031234567")
        self.assertEqual(normalize_phone("0803-123-4567"), "+2348031234567")

    def test_accepts_a_number_that_already_carries_the_country_code(self):
        self.assertEqual(normalize_phone("+234 803 123 4567"), "+2348031234567")

    def test_every_spelling_of_one_number_collapses_to_the_same_value(self):
        spellings = ["08031234567", "0803 123 4567", "+2348031234567", "+234 803 123 4567"]

        self.assertEqual({normalize_phone(s) for s in spellings}, {"+2348031234567"})

    def test_preserves_a_valid_non_nigerian_number(self):
        self.assertEqual(normalize_phone("+442071838750"), "+442071838750")

    def test_rejects_a_number_that_is_not_dialable(self):
        with self.assertRaises(ValidationError):
            normalize_phone("0800000")

    def test_rejects_empty_input(self):
        with self.assertRaises(ValidationError):
            normalize_phone("   ")

    def test_rejects_text(self):
        with self.assertRaises(ValidationError):
            normalize_phone("not a phone")
