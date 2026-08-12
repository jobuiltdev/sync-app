import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { Address } from '@/api/endpoints/addresses';
import { Button } from '@/components/ui/Button';
import { useAddresses, useService, useServiceProviders } from '@/features/catalog/hooks';
import { formatNaira } from '@/lib/money';
import { SpecFields } from '@/features/bookings/SpecFields';
import { useCreateBooking } from '@/features/bookings/hooks';
import {
  type SpecValue,
  buildSpecSchema,
  initialSpecValues,
  toRequestDetails,
} from '@/features/bookings/spec-form';
import { toVerificationBlock } from '@/features/bookings/verification';
import { toFormErrors } from '@/features/auth/form-errors';
import { MIN_TOUCH_TARGET, colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Booking flow.
 *
 * The fields between "where" and "book" are whatever the service declares. This
 * screen has no idea what a cleaning or a dispatch needs, which is what lets a new
 * vertical appear without an app release.
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

  function submit() {
    if (!service.data || !chosenAddress || !chosenProvider) return;

    const parsed = specSchema.safeParse(current);
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
        details: toRequestDetails(schema, current),
      },
      { onSuccess: (booking) => router.replace(`/booking/${booking.id}`) },
    );
  }

  if (service.isPending || addresses.isPending || providers.isPending) {
    return (
      <SafeAreaView style={styles.centred}>
        <ActivityIndicator color={colors.accent} />
      </SafeAreaView>
    );
  }

  if (service.error) {
    return (
      <SafeAreaView style={styles.centred}>
        <Text style={styles.body}>{service.error.message}</Text>
      </SafeAreaView>
    );
  }

  const hasAddress = saved.length > 0;
  const hasProvider = available.length > 0;

  return (
    <SafeAreaView style={styles.screen}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <Text style={styles.title}>{service.data.name}</Text>
            {service.data.summary ? (
              <Text style={styles.muted}>{service.data.summary}</Text>
            ) : null}
          </View>

          {verification ? (
            <View accessibilityRole="alert" style={[styles.card, styles.cardWarn]}>
              <Text style={styles.cardTitle}>One step first</Text>
              <Text style={styles.body}>{verification.message}</Text>
              <Button
                label="Verify my phone number"
                onPress={() => router.push('/verify-phone')}
              />
            </View>
          ) : null}

          {apiErrors.message ? (
            <View accessibilityRole="alert" style={[styles.card, styles.cardError]}>
              <Text style={styles.body}>{apiErrors.message}</Text>
            </View>
          ) : null}

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Who</Text>
            {!hasProvider ? (
              <View style={styles.card}>
                <Text style={styles.body}>
                  Nobody is offering this service yet. Try another service for now.
                </Text>
              </View>
            ) : (
              available.map((option) => (
                <Pressable
                  key={option.id}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: chosenProvider?.id === option.id }}
                  accessibilityLabel={`${option.display_name}, ${formatNaira(option.price_kobo)}`}
                  onPress={() => setProviderId(option.id)}
                  style={[styles.option, chosenProvider?.id === option.id && styles.optionSelected]}
                >
                  <View style={styles.optionRow}>
                    <Text style={styles.optionTitle}>{option.display_name}</Text>
                    <Text style={styles.price}>{formatNaira(option.price_kobo)}</Text>
                  </View>
                  {option.bio ? <Text style={styles.muted}>{option.bio}</Text> : null}
                </Pressable>
              ))
            )}
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Where</Text>
            {!hasAddress ? (
              <View style={styles.card}>
                <Text style={styles.body}>
                  You have not saved an address yet. Add one from your account before booking.
                </Text>
              </View>
            ) : (
              saved.map((address) => (
                <AddressOption
                  key={address.id}
                  address={address}
                  selected={chosenAddress?.id === address.id}
                  onPress={() => setAddressId(address.id)}
                />
              ))
            )}
          </View>

          {schema ? (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Details</Text>
              <SpecFields
                schema={schema}
                values={current}
                errors={fieldErrors}
                onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
              />
            </View>
          ) : null}

          <Button
            label="Book this service"
            loading={create.isPending}
            disabled={!hasAddress || !hasProvider}
            onPress={submit}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
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
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      accessibilityLabel={`${address.street_address}, ${address.landmark}`}
      onPress={onPress}
      style={[styles.option, selected && styles.optionSelected]}
    >
      <Text style={styles.optionTitle}>{address.street_address}</Text>
      <Text style={styles.muted}>{address.landmark}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  flex: { flex: 1 },
  centred: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.ground,
    padding: spacing.xl,
  },
  content: { padding: spacing.xl, gap: spacing.xl },
  header: { gap: spacing.xs, paddingTop: spacing.lg },
  title: {
    fontSize: fontSizes.title2,
    fontWeight: fontWeights.bold,
    color: colors.ink,
    letterSpacing: -0.5,
  },
  section: { gap: spacing.sm },
  sectionTitle: {
    fontSize: fontSizes.callout,
    fontWeight: fontWeights.semibold,
    color: colors.ink,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    padding: spacing.lg,
    gap: spacing.md,
  },
  cardWarn: { borderColor: colors.warning, backgroundColor: colors.surfaceSunk },
  cardError: { borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  option: {
    minHeight: MIN_TOUCH_TARGET,
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    padding: spacing.lg,
    gap: 2,
  },
  optionSelected: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  optionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.md,
  },
  price: {
    fontSize: fontSizes.footnote,
    fontWeight: fontWeights.semibold,
    color: colors.accent,
    fontVariant: ['tabular-nums'],
  },
  optionTitle: { fontSize: fontSizes.body, fontWeight: fontWeights.medium, color: colors.ink },
});
