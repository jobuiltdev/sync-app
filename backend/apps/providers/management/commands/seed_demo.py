"""The demo marketplace, as it should look when somebody is watching.

Two jobs. Put one polished provider in place who can take any job in the catalog,
and get the generated load-test accounts out of the customer's way.

Everything here is **idempotent and non-destructive**. No account is deleted, no
booking is touched, and no verification attempt is created or altered: clutter is
removed by deactivating a provider's offer of a service, which is the same switch
a real provider uses when they stop offering something. The rows survive, their
history resolves, and running this twice changes nothing the second time.

It is a development convenience and refuses to run against production settings.
Nothing in it relaxes a rule: approval, eligibility and matching are untouched,
and the demo provider satisfies them the way any provider must.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Service
from apps.providers.models import ProviderProfile, ProviderService, ProviderServiceArea

#: The provider an investor sees. Renamed from "Ada Cleaning Services", which
#: named one category on an account that now offers all of them.
DEMO_PROVIDER_EMAIL = "ada.okeke@example.com"
DEMO_PROVIDER_NAME = "Ada Services"
DEMO_PROVIDER_BIO = (
    "Full service across Lagos. Cleaning, laundry, errands, beauty, home repairs "
    "and same day delivery."
)

#: Where the demo provider works. Matching is by state, so one row covers the
#: whole demo.
DEMO_STATE = "LAGOS"

#: Generated during M4, M5 and M6 load and matching work. They are real rows with
#: real history, so they are left alone except for being taken out of the shop
#: window.
GENERATED_NAME_PREFIXES: tuple[str, ...] = ("M4-", "M5 ", "M6 ", "M6B ", "Live Cleaning ")

#: A marketplace needs more than one name in it.
#:
#: Hiding the generated accounts leaves Ada alone on every cleaning search, and a
#: category with a single provider does not read as a marketplace. These three
#: are plainly demo accounts on example.com, they offer cleaning only, and they
#: exist so the customer has a choice to make on screen.
SUPPORTING_PROVIDERS: tuple[tuple[str, str, str], ...] = (
    (
        "demo.brightspaces@example.com",
        "Bright Spaces",
        "Small team, mostly apartments in Lekki and Victoria Island.",
    ),
    (
        "demo.freshstart@example.com",
        "Fresh Start Cleaning",
        "Deep cleans and post construction work. Ten years on the island.",
    ),
    (
        "demo.homeandhearth@example.com",
        "Home and Hearth",
        "Weekly and fortnightly upkeep for homes and small offices.",
    ),
)

#: What the supporting providers offer. Cleaning only: they exist to populate one
#: category, and putting them everywhere would bury the demo provider.
SUPPORTING_SERVICE_SLUGS: tuple[str, ...] = ("standard-clean",)


class Command(BaseCommand):
    help = "Sets up the demo marketplace. Development only, safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-generated",
            action="store_true",
            help="Leave the generated M4/M5/M6 providers visible.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo is a development convenience and will not run with "
                "DEBUG off. Demo data does not belong in production."
            )

        profile = self._demo_provider()
        offered = self._offer_everything(profile)
        covered = self._cover_state(profile)

        supporting = self._supporting_providers()
        hidden = 0 if options["keep_generated"] else self._hide_generated(profile)

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo ready: {profile.display_name} offers {offered} services "
                f"across {covered} area(s), {supporting} supporting provider(s), "
                f"{hidden} generated offering(s) hidden."
            )
        )

    def _supporting_providers(self) -> int:
        """The other names on a cleaning search.

        Adopts an existing account by email if one is there, so re-running never
        makes a second Bright Spaces.
        """
        User = get_user_model()
        services = list(Service.objects.filter(slug__in=SUPPORTING_SERVICE_SLUGS))

        for email, name, bio in SUPPORTING_PROVIDERS:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"first_name": name.split()[0]},
            )
            if created:
                # Reachable only through this seed, and never as a login.
                user.set_unusable_password()
            if not user.is_phone_verified:
                user.phone_verified_at = _now()
            if not user.is_email_verified:
                user.email_verified_at = _now()
            user.save()

            profile, _ = ProviderProfile.objects.get_or_create(
                user=user,
                defaults={"display_name": name, "bio": bio},
            )
            if (profile.display_name, profile.bio, profile.is_accepting_jobs) != (
                name,
                bio,
                True,
            ):
                profile.display_name = name
                profile.bio = bio
                profile.is_accepting_jobs = True
                profile.save(
                    update_fields=["display_name", "bio", "is_accepting_jobs", "updated_at"]
                )

            _approve(profile)

            ProviderServiceArea.objects.get_or_create(provider=profile, state=DEMO_STATE, lga="")
            for service in services:
                offering, made = ProviderService.objects.get_or_create(
                    provider=profile, service=service, defaults={"is_active": True}
                )
                if not made and not offering.is_active:
                    offering.is_active = True
                    offering.save(update_fields=["is_active", "updated_at"])

        return len(SUPPORTING_PROVIDERS)

    def _demo_provider(self) -> ProviderProfile:
        """The demo provider, approved and taking work.

        `verification_status` is set through the lifecycle rather than assigned,
        so this cannot put a provider into a state the product itself forbids. A
        seeded demo account starts at PENDING and walks the same two steps a real
        one does.
        """
        User = get_user_model()

        try:
            user = User.objects.get(email=DEMO_PROVIDER_EMAIL)
        except User.DoesNotExist as exc:
            raise CommandError(
                f"No account for {DEMO_PROVIDER_EMAIL}. This seed adopts the existing "
                "demo account rather than creating one, so that its bookings survive."
            ) from exc

        # A provider cannot accept work without both contacts confirmed. The demo
        # account is ours, so it is marked confirmed here rather than sent an OTP.
        contact_fields = []
        if not user.is_phone_verified:
            user.phone_verified_at = user.phone_verified_at or _now()
            contact_fields.append("phone_verified_at")
        if not user.is_email_verified:
            user.email_verified_at = user.email_verified_at or _now()
            contact_fields.append("email_verified_at")
        if contact_fields:
            user.save(update_fields=[*contact_fields, "updated_at"])

        profile, _ = ProviderProfile.objects.get_or_create(
            user=user,
            defaults={"display_name": DEMO_PROVIDER_NAME},
        )

        changed = []
        if profile.display_name != DEMO_PROVIDER_NAME:
            profile.display_name = DEMO_PROVIDER_NAME
            changed.append("display_name")
        if profile.bio != DEMO_PROVIDER_BIO:
            profile.bio = DEMO_PROVIDER_BIO
            changed.append("bio")
        if not profile.is_accepting_jobs:
            profile.is_accepting_jobs = True
            changed.append("is_accepting_jobs")
        if changed:
            profile.save(update_fields=[*changed, "updated_at"])

        _approve(profile)
        return profile

    def _offer_everything(self, profile: ProviderProfile) -> int:
        """Every active service, so no demo path dead-ends at "nobody offers this".

        Reactivates an offering that was switched off rather than making a second
        one, because the pair is unique per provider and service.
        """
        count = 0
        for service in Service.objects.filter(is_active=True):
            offering, created = ProviderService.objects.get_or_create(
                provider=profile,
                service=service,
                defaults={"is_active": True},
            )
            if not created and not offering.is_active:
                offering.is_active = True
                offering.save(update_fields=["is_active", "updated_at"])
            count += 1

        return count

    def _cover_state(self, profile: ProviderProfile) -> int:
        ProviderServiceArea.objects.get_or_create(provider=profile, state=DEMO_STATE, lga="")
        return profile.service_areas.count()

    def _hide_generated(self, keep: ProviderProfile) -> int:
        """Take the generated accounts out of the marketplace.

        Their offerings are deactivated, not deleted, and the accounts, bookings
        and verification history are untouched. `--keep-generated` puts them back
        in view for anyone debugging matching.
        """
        generated = ProviderProfile.objects.filter(_name_matches(GENERATED_NAME_PREFIXES)).exclude(
            pk=keep.pk
        )

        return ProviderService.objects.filter(provider__in=generated, is_active=True).update(
            is_active=False
        )


def _approve(profile: ProviderProfile) -> None:
    """Walk the demo provider to APPROVED through the real lifecycle."""
    from apps.providers.models import VerificationStatus

    if profile.verification_status == VerificationStatus.APPROVED:
        return

    if profile.verification_status in {
        VerificationStatus.PENDING,
        VerificationStatus.REJECTED,
    }:
        profile.transition_verification(VerificationStatus.UNDER_REVIEW)

    profile.transition_verification(VerificationStatus.APPROVED)


def _name_matches(prefixes: tuple[str, ...]):
    from django.db.models import Q

    query = Q(pk__in=[])
    for prefix in prefixes:
        query |= Q(display_name__startswith=prefix)
    return query


def _now():
    from django.utils import timezone

    return timezone.now()
