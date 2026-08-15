import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { Address } from '@/api/endpoints/addresses';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { useAddresses, useCreateAddress, useDeleteAddress } from '@/features/catalog/hooks';
import { NIGERIAN_STATES, stateLabel } from '@/lib/nigeria';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Where a customer's work happens.
 *
 * The landmark is prominent rather than optional, and the API requires it, for a
 * reason particular to here: Nigerian street addresses are frequently unusable
 * and a landmark is what a provider actually navigates by.
 *
 * A booking copies the address it was made with rather than pointing at it, so
 * editing or deleting one of these never rewrites the history of a job that has
 * already happened.
 */
export default function AddressesScreen() {
  const router = useRouter();
  const addresses = useAddresses();
  const create = useCreateAddress();
  const remove = useDeleteAddress();

  const [street, setStreet] = useState('');
  const [landmark, setLandmark] = useState('');
  const [area, setArea] = useState('');
  const [lga, setLga] = useState('');
  const [state, setState] = useState('LAGOS');
  const [directions, setDirections] = useState('');
  const [adding, setAdding] = useState(false);

  const saved = addresses.data?.results ?? [];
  const complete = street.trim().length > 0 && landmark.trim().length > 0;

  const submit = () => {
    if (!complete) return;

    create.mutate(
      {
        street_address: street.trim(),
        landmark: landmark.trim(),
        area: area.trim(),
        lga: lga.trim(),
        state,
        directions_note: directions.trim(),
        is_default: saved.length === 0,
      },
      {
        onSuccess: () => {
          setStreet('');
          setLandmark('');
          setArea('');
          setLga('');
          setDirections('');
          setAdding(false);
        },
      },
    );
  };

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <Text style={styles.title}>Your addresses</Text>
          <Text style={styles.muted}>Where a provider comes to do the work.</Text>
        </View>

        {addresses.isPending ? (
          <View style={styles.card}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : addresses.error ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not load your addresses</Text>
            <Text style={styles.body}>{addresses.error.message}</Text>
            <Button label="Try again" variant="secondary" onPress={() => addresses.refetch()} />
          </View>
        ) : saved.length === 0 ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>No addresses yet</Text>
            <Text style={styles.body}>Add one so you can book a service.</Text>
          </View>
        ) : (
          saved.map((address) => (
            <AddressRow
              key={address.id}
              address={address}
              onDelete={() => remove.mutate(address.id)}
              deleting={remove.isPending}
            />
          ))
        )}

        {remove.error ? (
          <View accessibilityRole="alert" style={[styles.card, styles.cardError]}>
            <Text style={styles.body}>{remove.error.message}</Text>
          </View>
        ) : null}

        {adding ? (
          <View style={styles.form}>
            <Field
              label="Street address"
              value={street}
              onChangeText={setStreet}
              placeholder="14 Adeola Odeku Street"
            />
            <Field
              label="Landmark"
              value={landmark}
              onChangeText={setLandmark}
              placeholder="Opposite Eko Hotel gate"
              error={
                landmark.length === 0 && street.length > 0
                  ? 'A landmark is how your provider will find you.'
                  : undefined
              }
            />
            <Field label="Area" value={area} onChangeText={setArea} placeholder="Victoria Island" />
            <Field label="Local government" value={lga} onChangeText={setLga} placeholder="Eti-Osa" />

            <Text style={styles.label}>State</Text>
            <View style={styles.chips}>
              {NIGERIAN_STATES.map((option) => (
                <Pressable
                  key={option.value}
                  accessibilityRole="button"
                  accessibilityState={{ selected: state === option.value }}
                  accessibilityLabel={option.label}
                  onPress={() => setState(option.value)}
                  style={({ pressed }) => [
                    styles.chip,
                    state === option.value && styles.chipSelected,
                    pressed && styles.chipPressed,
                  ]}
                >
                  <Text
                    style={[styles.chipText, state === option.value && styles.chipTextSelected]}
                  >
                    {option.label}
                  </Text>
                </Pressable>
              ))}
            </View>

            <Field
              label="Directions (optional)"
              value={directions}
              onChangeText={setDirections}
              placeholder="Blue gate, second floor."
              multiline
            />

            {create.error ? (
              <View accessibilityRole="alert" style={[styles.card, styles.cardError]}>
                <Text style={styles.body}>{create.error.message}</Text>
              </View>
            ) : null}

            <Button
              label="Save address"
              loading={create.isPending}
              disabled={!complete}
              onPress={submit}
            />
            <Button label="Cancel" variant="secondary" onPress={() => setAdding(false)} />
          </View>
        ) : (
          <Button label="Add an address" onPress={() => setAdding(true)} />
        )}

        <Button label="Back" variant="secondary" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

function AddressRow({
  address,
  onDelete,
  deleting,
}: {
  address: Address;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <View style={styles.card}>
      <View style={styles.rowTop}>
        <Text style={styles.cardTitle}>{address.street_address}</Text>
        {address.is_default ? (
          <View style={styles.pill}>
            <Text style={styles.pillText}>Default</Text>
          </View>
        ) : null}
      </View>
      <Text style={styles.muted}>{address.landmark}</Text>
      <Text style={styles.muted}>
        {[address.area, address.lga, stateLabel(address.state)].filter(Boolean).join(', ')}
      </Text>
      {address.directions_note ? (
        <Text style={styles.muted}>{address.directions_note}</Text>
      ) : null}
      <Button label="Remove" variant="secondary" loading={deleting} onPress={onDelete} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  content: { padding: spacing.xl, gap: spacing.md },
  header: { gap: spacing.xs, paddingTop: spacing.lg, paddingBottom: spacing.sm },
  title: {
    fontSize: fontSizes.title1,
    fontWeight: fontWeights.bold,
    color: colors.ink,
    letterSpacing: -0.5,
  },
  form: { gap: spacing.lg },
  label: {
    fontSize: fontSizes.footnote,
    fontWeight: fontWeights.medium,
    color: colors.inkSoft,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  cardError: { borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  pill: {
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    borderRadius: radii.pill,
    backgroundColor: colors.accentSoft,
  },
  pillText: { fontSize: fontSizes.caption, fontWeight: fontWeights.medium, color: colors.accent },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radii.pill,
    backgroundColor: colors.surfaceSunk,
  },
  chipSelected: { backgroundColor: colors.accent },
  chipPressed: { opacity: 0.7 },
  chipText: { fontSize: fontSizes.caption, color: colors.inkSoft },
  chipTextSelected: { color: colors.onAccent, fontWeight: fontWeights.medium },
});
