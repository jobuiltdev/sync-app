"""Confirming that a payout destination is a real account.

Ten digits somebody typed is not an account. The check that distinguishes the two
is asking the bank what name it holds, and these cover what happens when it
answers, when it does not, and when the account underneath changes afterwards.
"""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.payments import services
from apps.payments.banks.base import BankLookupError
from apps.payments.banks.fake import FakeBankResolver
from apps.payments.banks.paystack import PaystackBankResolver
from apps.payments.destinations import DestinationStatus, PayoutDestination
from apps.payments.errors import (
    BankLookupFailed,
    DestinationNotVerified,
    InvalidPayoutDestination,
)
from apps.payments.gateways.base import GatewayError
from apps.payments.gateways.paystack import PaystackGateway
from apps.payments.payouts import PayoutRequest
from apps.payments.tests.factories import earn, earning_setup, make_destination

ACCOUNT = "0123456789"
BANK = "058"
NAME = "Adaeze Okonkwo"


class FakeResolverTests(SimpleTestCase):
    def setUp(self):
        FakeBankResolver.clear()
        self.resolver = FakeBankResolver()

    def test_it_resolves_an_account_a_test_has_arranged(self):
        FakeBankResolver.arrange(account_number=ACCOUNT, bank_code=BANK, account_name=NAME)

        resolved = self.resolver.resolve(account_number=ACCOUNT, bank_code=BANK)

        self.assertEqual(resolved.account_name, NAME)
        self.assertEqual(resolved.account_number_last4, "6789")

    def test_it_refuses_anything_nobody_arranged(self):
        # Deliberately not permissive. A resolver that said yes to everything
        # would let a test pass while the real check was broken.
        with self.assertRaises(BankLookupError):
            self.resolver.resolve(account_number=ACCOUNT, bank_code=BANK)

    def test_the_same_number_at_a_different_bank_is_a_different_account(self):
        FakeBankResolver.arrange(account_number=ACCOUNT, bank_code=BANK, account_name=NAME)

        with self.assertRaises(BankLookupError):
            self.resolver.resolve(account_number=ACCOUNT, bank_code="044")

    def test_it_returns_no_more_of_the_number_than_the_last_four_digits(self):
        FakeBankResolver.arrange(account_number=ACCOUNT, bank_code=BANK, account_name=NAME)

        resolved = self.resolver.resolve(account_number=ACCOUNT, bank_code=BANK)

        self.assertNotIn(ACCOUNT, str(resolved))

    def test_it_offers_banks_to_choose_from(self):
        banks = self.resolver.banks()

        self.assertTrue(banks)
        self.assertIn("058", [bank["code"] for bank in banks])


@override_settings(
    PAYSTACK={
        "SECRET_KEY": "sk_test_notarealkey",
        "PUBLIC_KEY": "",
        "CURRENCY": "NGN",
        "TIMEOUT_SECONDS": 5,
    }
)
class PaystackResolverTests(SimpleTestCase):
    """Translation only. Nothing here reaches the network."""

    def test_it_returns_the_name_the_bank_holds(self):
        with patch.object(
            PaystackGateway,
            "_request",
            return_value={"account_name": NAME, "account_number": ACCOUNT},
        ):
            resolved = PaystackBankResolver().resolve(account_number=ACCOUNT, bank_code=BANK)

        self.assertEqual(resolved.account_name, NAME)
        self.assertEqual(resolved.bank_code, BANK)

    def test_a_refusal_becomes_a_lookup_error(self):
        with (
            patch.object(
                PaystackGateway,
                "_request",
                side_effect=GatewayError("Could not resolve account name"),
            ),
            self.assertRaises(BankLookupError),
        ):
            PaystackBankResolver().resolve(account_number=ACCOUNT, bank_code=BANK)

    def test_an_empty_name_is_not_a_resolution(self):
        with (
            patch.object(PaystackGateway, "_request", return_value={"account_name": "  "}),
            self.assertRaises(BankLookupError),
        ):
            PaystackBankResolver().resolve(account_number=ACCOUNT, bank_code=BANK)

    def test_it_lists_banks(self):
        with patch.object(
            PaystackGateway,
            "_request",
            return_value=[{"code": "058", "name": "GTBank"}, {"code": "", "name": "broken"}],
        ):
            banks = PaystackBankResolver().banks()

        self.assertEqual(banks, [{"code": "058", "name": "GTBank"}])

    @override_settings(PAYSTACK={"SECRET_KEY": "", "PUBLIC_KEY": "", "CURRENCY": "NGN"})
    def test_it_refuses_to_be_built_without_credentials(self):
        with self.assertRaises(BankLookupError):
            PaystackBankResolver()


class DestinationVerificationTests(TestCase):
    def setUp(self):
        FakeBankResolver.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]

    def save_account(self, **overrides):
        return make_destination(self.provider, verified=False, **overrides)

    def test_a_saved_account_starts_unverified(self):
        destination = self.save_account()

        self.assertEqual(destination.verification_status, DestinationStatus.UNVERIFIED)
        self.assertFalse(destination.is_verified)
        self.assertFalse(destination.is_usable)

    def test_verifying_records_the_name_the_bank_returned(self):
        self.save_account()
        FakeBankResolver.arrange(account_number=ACCOUNT, bank_code=BANK, account_name=NAME)

        destination = services.verify_destination(self.provider, ACCOUNT)

        self.assertEqual(destination.verification_status, DestinationStatus.VERIFIED)
        self.assertEqual(destination.resolved_account_name, NAME)
        self.assertIsNotNone(destination.verified_at)
        self.assertTrue(destination.is_usable)

    def test_the_bank_answer_is_kept_separate_from_what_the_provider_typed(self):
        # Showing both back is what lets somebody notice they have typed their
        # sister's account number.
        self.save_account(account_name="Ada O")
        FakeBankResolver.arrange(
            account_number=ACCOUNT, bank_code=BANK, account_name="ADAEZE N OKONKWO"
        )

        destination = services.verify_destination(self.provider, ACCOUNT)

        self.assertEqual(destination.account_name, "Ada O")
        self.assertEqual(destination.resolved_account_name, "ADAEZE N OKONKWO")

    def test_an_account_the_bank_does_not_recognise_is_refused(self):
        self.save_account()

        with self.assertRaises(BankLookupFailed):
            services.verify_destination(self.provider, ACCOUNT)

    def test_a_failed_lookup_leaves_the_destination_unverified_rather_than_failed(self):
        # A bank outage must not look to the provider like a wrong account number
        # that they then go and 'fix'.
        self.save_account()

        with self.assertRaises(BankLookupFailed):
            services.verify_destination(self.provider, ACCOUNT)

        destination = PayoutDestination.objects.get(provider=self.provider)
        self.assertEqual(destination.verification_status, DestinationStatus.UNVERIFIED)

    def test_verifying_a_number_that_is_not_the_one_on_file_is_refused(self):
        # The hash is what makes this checkable at all: the stored row cannot be
        # compared against a number it does not hold, so it is compared by hash.
        self.save_account()
        FakeBankResolver.arrange(account_number="9999999999", bank_code=BANK, account_name=NAME)

        with self.assertRaises(InvalidPayoutDestination):
            services.verify_destination(self.provider, "9999999999")

    def test_verifying_without_a_destination_on_file_is_refused(self):
        with self.assertRaises(InvalidPayoutDestination):
            services.verify_destination(self.provider, ACCOUNT)


class VerificationInvalidationTests(TestCase):
    """A verification is a statement about one number at one bank."""

    def setUp(self):
        FakeBankResolver.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        self.destination = make_destination(self.provider)

    def test_it_starts_verified(self):
        self.assertTrue(self.destination.is_verified)

    def test_changing_the_account_number_throws_the_verification_away(self):
        updated = make_destination(self.provider, verified=False, account_number="0000000001")

        self.assertEqual(updated.verification_status, DestinationStatus.UNVERIFIED)
        self.assertEqual(updated.resolved_account_name, "")
        self.assertIsNone(updated.verified_at)
        self.assertFalse(updated.is_usable)

    def test_changing_the_bank_throws_the_verification_away(self):
        # The same number at a different bank is a different account.
        updated = make_destination(self.provider, verified=False, bank_code="044")

        self.assertFalse(updated.is_verified)

    def test_resaving_the_identical_account_still_needs_confirming_again(self):
        # Cheap to redo, and the alternative is a rule about when a save counts
        # as a change, which is a rule that eventually gets it wrong.
        updated = make_destination(self.provider, verified=False)

        self.assertFalse(updated.is_verified)

    def test_a_payout_is_refused_once_the_destination_changes(self):
        earn(self.setup)
        make_destination(self.provider, verified=False, account_number="0000000001")

        with self.assertRaises(DestinationNotVerified):
            services.request_payout(
                provider=self.provider, actor=self.provider.user, amount_kobo=100_000
            )

        self.assertEqual(PayoutRequest.objects.count(), 0)

    def test_reconfirming_the_new_account_unblocks_the_payout(self):
        earn(self.setup)
        make_destination(self.provider, verified=False, account_number="0000000001")
        FakeBankResolver.arrange(account_number="0000000001", bank_code=BANK, account_name=NAME)
        services.verify_destination(self.provider, "0000000001")

        payout = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=100_000
        )

        self.assertEqual(payout.amount_kobo, 100_000)


class UnverifiedPayoutTests(TestCase):
    def setUp(self):
        FakeBankResolver.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        earn(self.setup)

    def test_an_unverified_destination_cannot_be_paid_to(self):
        make_destination(self.provider, verified=False)

        with self.assertRaises(DestinationNotVerified):
            services.request_payout(
                provider=self.provider, actor=self.provider.user, amount_kobo=100_000
            )

    def test_a_missing_destination_is_a_different_refusal_from_an_unconfirmed_one(self):
        # They need different things from the provider: one an account added, the
        # other the one on file confirmed.
        with self.assertRaises(InvalidPayoutDestination):
            services.request_payout(
                provider=self.provider, actor=self.provider.user, amount_kobo=100_000
            )
