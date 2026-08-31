import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import type { Address } from '@/api/endpoints/addresses';
import type { ServiceProvider } from '@/api/endpoints/catalog';
import { Avatar } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { Header } from '@/components/ui/Header';
import { Icon } from '@/components/ui/Icon';
import { Screen } from '@/components/ui/Screen';
import { Skeleton } from '@/components/ui/Skeleton';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { BlockedState, EmptyState, ErrorState, InlineError } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { toFormErrors } from '@/features/auth/form-errors';
import { SpecFields } from '@/features/bookings/SpecFields';
import { useCreateBooking } from '@/features/bookings/hooks';
import {
  type SpecValue,
  buildSpecSchema,
  initialSpecValues,
  optionsDeltaKobo,
  toRequestDetails,
  toSpecFieldErrors,
  withDrafts,
} from '@/features/bookings/spec-form';
import { toVerificationBlock } from '@/features/bookings/verification';
import { useAddresses, useService, useServiceProviders } from '@/features/catalog/hooks';
import { formatNaira, formatPriceFrom } from '@/lib/money';
import { usePalette } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

/**
 * Booking: a confident, simple checkout.
 *
 * Six questions in the order a person asks them: what am I buying, who is doing
 * it, where, what do you need to know, what does it cost, what happens next. The
 * price is pinned in a footer above the primary action so the answer to "what
 * does it cost" is never more than a glance away, however long the spec form is.
 *
 * The fields between "where" and "book" are whatever the service declares. This
 * screen has no idea what a cleaning or a dispatch needs, which is what lets a
 * new vertical appear without an app release.
 */
export default function BookServiceScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const router = useRouter();

  const service = useService(slug);
  const addresses = useAddresses();
  const providers = useServiceProviders(slug);
  const create = useCreateBooking();

  const schema = service.data?.details_schema;
  const [values, setValues] = useState<Record<string, SpecValue>>({});
  // Text typed into a list field but not yet added. Held here so that submitting
  // counts it rather than throwing it away.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [addressId, setAddressId] = useState<string | null>(null);
  const [providerId, setProviderId] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const specSchema = useMemo(() => buildSpecSchema(schema), [schema]);
  const defaults = useMemo(() => initialSpecValues(schema), [schema]);
  const current = { ...defaults, ...values };

  const saved = addresses.data?.results ?? [];
  const chosenAddress =
    saved.find((a) => a.id === addressId) ?? saved.find((a) => a.is_default) ?? saved[0];

  const available = providers.data ?? [];
  const chosenProvider = available.find((p) => p.id === providerId) ?? available[0];

  const verification = toVerificationBlock(create.error);
  const apiErrors = verification ? { fields: {}, message: null } : toFormErrors(create.error);
  // Errors the server raised against the vertical's own fields. They arrive one
  // level deeper than the generic mapper looks, so without this a rejected
  // booking showed nothing anywhere on the screen.
  const specErrors = verification ? {} : toSpecFieldErrors(create.error);
  const shownErrors = { ...specErrors, ...fieldErrors };

  // One line beside the button. The banner at the top of the form is out of
  // sight by the time somebody reaches the action on a long spec, so a rejection
  // that only rendered up there read as nothing happening at all.
  // Covers a local rejection too: the form can refuse to submit without the
  // customer seeing why, if the offending field has scrolled off screen.
  const failure =
    Object.keys(shownErrors).length > 0
      ? 'Check the highlighted answers above.'
      : create.isError
        ? (apiErrors.message ?? 'That did not go through. Please try again.')
        : null;

  function submit() {
    if (!service.data || !chosenAddress || !chosenProvider) return;

    // Anything half-typed into a list field counts as an answer.
    const answers = withDrafts(schema, current, drafts);

    const parsed = specSchema.safeParse(answers);
    if (!parsed.success) {
      const next: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const key = String(issue.path[0]);
        if (key && !next[key]) next[key] = issue.message;
      }
      setFieldErrors(next);
      return;
    }

    setFieldErrors({});
    create.mutate(
      {
        service_slug: service.data.slug,
        provider_id: chosenProvider.id,
        address_id: chosenAddress.id,
        details: toRequestDetails(schema, answers),
      },
      { onSuccess: (booking) => router.replace(`/booking/${booking.id}`) },
    );
  }

  if (service.isPending || addresses.isPending || providers.isPending) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <View style={styles.loading}>
          <Skeleton width="60%" height={30} />
          <Skeleton width="85%" height={20} />
          <Skeleton width="100%" height={110} radius={18} />
          <Skeleton width="100%" height={110} radius={18} />
        </View>
      </Screen>
    );
  }

  if (service.error) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <ErrorState error={service.error} onRetry={() => void service.refetch()} />
      </Screen>
    );
  }

  const hasAddress = saved.length > 0;
  const hasProvider = available.length > 0;
  const ready = hasAddress && hasProvider;
  // What the customer will actually be charged, once a provider is chosen: their
  // price, not the service's base, plus whatever their answers add. A deep clean
  // costs more than a standard one, and the footer says so the moment they tap
  // it rather than after they have booked.
  //
  // Still a preview. The booking's real total is fixed by the server, from the
  // same option rows this figure is built from.
  const base = chosenProvider?.price_kobo ?? service.data.base_price_kobo;
  const extras = optionsDeltaKobo(schema, current);
  const preview = base + extras;

  return (
    <Screen
      footer={
        ready ? (
          <>
            <View style={styles.total}>
              <Text variant="footnote" tone="muted">
                {extras ? `Total, including ${formatNaira(extras)} extras` : 'Total'}
              </Text>
              <Text variant="price" weight="bold">
                {formatNaira(preview)}
              </Text>
            </View>
            {failure ? (
              <Text variant="caption" tone="danger" accessibilityRole="alert">
                {failure}
              </Text>
            ) : null}
            <Button
              label="Book this service"
              loading={create.isPending}
              onPress={submit}
            />
          </>
        ) : undefined
      }
    >
      <Header onBack={() => router.back()} />

      <View style={styles.head}>
        <Text variant="title1" accessibilityRole="header">
          {service.data.name}
        </Text>
        {service.data.summary ? (
          <Text variant="body" tone="muted">
            {service.data.summary}
          </Text>
        ) : null}
        <Text variant="footnote" tone="primary" weight="semibold">
          {formatPriceFrom(service.data.base_price_kobo, service.data.pricing_model)}
        </Text>
      </View>

      {verification ? (
        <BlockedState
          title="One step first"
          body={verification.message}
          action={
            <Button
              label="Verify my phone number"
              onPress={() => router.push('/verify-phone')}
            />
          }
        />
      ) : null}

      {apiErrors.message ? <InlineError error={create.error} /> : null}

      <View style={styles.section}>
        <SectionHeader title="Who" />
        {!hasProvider ? (
          <EmptyState
            icon="profile"
            title="Nobody offers this yet"
            body="No approved provider covers this service in your area. Try another service for now."
          />
        ) : (
          <View style={styles.options}>
            {available.map((option) => (
              <ProviderOption
                key={option.id}
                provider={option}
                selected={chosenProvider?.id === option.id}
                onPress={() => setProviderId(option.id)}
              />
            ))}
          </View>
        )}
      </View>

      <View style={styles.section}>
        <SectionHeader title="Where" />
        {!hasAddress ? (
          <BlockedState
            icon="pin"
            title="No address saved"
            body="Add the place this should happen. The landmark matters more than the street."
            action={<Button label="Add an address" onPress={() => router.push('/addresses')} />}
          />
        ) : (
          <View style={styles.options}>
            {saved.map((address) => (
              <AddressOption
                key={address.id}
                address={address}
                selected={chosenAddress?.id === address.id}
                onPress={() => setAddressId(address.id)}
              />
            ))}
          </View>
        )}
      </View>

      {schema && schema.fields.length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="Details" />
          <Card>
            <SpecFields
              schema={schema}
              values={current}
              errors={shownErrors}
              onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
              drafts={drafts}
              onDraftChange={(name, draft) => setDrafts((prev) => ({ ...prev, [name]: draft }))}
            />
          </Card>
        </View>
      ) : null}

      <Text variant="caption" tone="muted">
        You are not charged yet. Payment happens after you book, and the price is
        fixed when the booking is made.
      </Text>
    </Screen>
  );
}

/** A selectable option. Selection is a border and a check, never a tint alone. */
function Selectable({
  selected,
  onPress,
  accessibilityLabel,
  children,
}: {
  selected: boolean;
  onPress: () => void;
  accessibilityLabel: string;
  children: React.ReactNode;
}) {
  const palette = usePalette();

  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      style={({ pressed }) => [
        styles.option,
        {
          backgroundColor: selected ? palette.primarySoft : palette.surface,
          borderColor: selected ? palette.primary : palette.hairline,
          borderWidth: selected ? 2 : StyleSheet.hairlineWidth * 2,
          opacity: pressed ? 0.85 : 1,
        },
      ]}
    >
      {children}
      {selected ? (
        <View style={styles.tick}>
          <Icon name="check" size={17} color={palette.primary} strokeWidth={2.4} />
        </View>
      ) : null}
    </Pressable>
  );
}

function ProviderOption({
  provider,
  selected,
  onPress,
}: {
  provider: ServiceProvider;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Selectable
      selected={selected}
      onPress={onPress}
      accessibilityLabel={`${provider.display_name}, ${formatNaira(provider.price_kobo)}`}
    >
      <View style={styles.optionRow}>
        <Avatar name={provider.display_name} size={40} />
        <View style={styles.optionText}>
          <Text variant="body" weight="semibold" numberOfLines={1}>
            {provider.display_name}
          </Text>
          {provider.experience_years ? (
            <Text variant="caption" tone="muted">
              {provider.experience_years} year{provider.experience_years === 1 ? '' : 's'} experience
            </Text>
          ) : null}
          {provider.bio ? (
            <Text variant="caption" tone="muted" numberOfLines={2}>
              {provider.bio}
            </Text>
          ) : null}
        </View>
        <Text variant="price" tone="primary">
          {formatNaira(provider.price_kobo)}
        </Text>
      </View>
    </Selectable>
  );
}

function AddressOption({
  address,
  selected,
  onPress,
}: {
  address: Address;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Selectable
      selected={selected}
      onPress={onPress}
      accessibilityLabel={`${address.street_address}, ${address.landmark}`}
    >
      <View style={styles.optionText}>
        <Text variant="body" weight="medium" numberOfLines={1}>
          {address.street_address}
        </Text>
        <Text variant="footnote" tone="soft" numberOfLines={1}>
          {address.landmark}
        </Text>
        <Text variant="caption" tone="muted">
          {[address.area, address.state].filter(Boolean).join(', ')}
        </Text>
      </View>
    </Selectable>
  );
}

const styles = StyleSheet.create({
  loading: { gap: spacing.lg },
  head: { gap: spacing.xs },
  section: { gap: spacing.md },
  options: { gap: spacing.sm },
  option: { borderRadius: radii.card, padding: spacing.lg },
  optionRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  optionText: { flex: 1, gap: spacing.xxs },
  tick: { position: 'absolute', top: spacing.sm, right: spacing.sm },
  total: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
});
