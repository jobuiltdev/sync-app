import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { eligibilityGaps, verificationStatusLabel } from '@/api/endpoints/providers';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { useCurrentUser } from '@/features/auth/hooks';
import { useCategories } from '@/features/catalog/hooks';
import {
  useAddProviderArea,
  useAddProviderService,
  useCreateProviderProfile,
  useProviderAreas,
  useProviderProfile,
  useProviderServices,
  useRemoveProviderArea,
  useRemoveProviderService,
  useUpdateProviderProfile,
} from '@/features/providers/hooks';
import { NIGERIAN_STATES } from '@/lib/nigeria';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Becoming a provider, and staying eligible for work.
 *
 * Everything here reflects server state. Approval in particular is adjudicated
 * and never self-declared: the API refuses to accept a verification status, so
 * this screen shows the one it was given and offers nothing to change it.
 *
 * The eligibility list is advisory. Dispatch decides who gets an offer, and this
 * exists so a provider waiting for work can see what is missing rather than
 * wondering why nothing arrives.
 */
export default function ProviderScreen() {
  const router = useRouter();
  const { data: user } = useCurrentUser();

  const profile = useProviderProfile();
  const hasProfile = Boolean(profile.data);
  const services = useProviderServices(hasProfile);
  const areas = useProviderAreas(hasProfile);
  const categories = useCategories();

  const create = useCreateProviderProfile();
  const update = useUpdateProviderProfile();
  const addService = useAddProviderService();
  const removeService = useRemoveProviderService();
  const addArea = useAddProviderArea();
  const removeArea = useRemoveProviderArea();

  const [displayName, setDisplayName] = useState('');
  const [bio, setBio] = useState('');

  if (profile.isPending) {
    return (
      <SafeAreaView style={styles.centred}>
        <ActivityIndicator color={colors.accent} />
      </SafeAreaView>
    );
  }

  // No profile is an ordinary state, not an error: most accounts are customers.
  if (!profile.data) {
    return (
      <SafeAreaView style={styles.screen}>
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.header}>
            <Text style={styles.title}>Work with Sync</Text>
            <Text style={styles.muted}>
              Take jobs from customers near you. Your account stays the same; this adds
              the provider side of it.
            </Text>
          </View>

          <Field
            label="Name customers will see"
            value={displayName}
            onChangeText={setDisplayName}
            placeholder="Ada Cleaning Services"
            autoCapitalize="words"
          />
          <Field
            label="About your work (optional)"
            value={bio}
            onChangeText={setBio}
            placeholder="Ten years of deep cleaning across Lagos Island."
            multiline
          />

          {create.error ? (
            <View style={[styles.card, styles.cardError]}>
              <Text style={styles.body}>{create.error.message}</Text>
            </View>
          ) : null}

          <Button
            label="Create provider profile"
            loading={create.isPending}
            disabled={displayName.trim().length === 0}
            onPress={() =>
              create.mutate({ display_name: displayName.trim(), bio: bio.trim() })
            }
          />
          <Button label="Back" variant="secondary" onPress={() => router.back()} />
        </ScrollView>
      </SafeAreaView>
    );
  }

  const gaps = eligibilityGaps(
    profile.data,
    services.data,
    areas.data,
    user?.is_phone_verified ?? false,
    user?.is_email_verified ?? false,
  );
  const listed = new Set((services.data ?? []).map((service) => service.service_slug));
  const covered = new Set((areas.data ?? []).map((area) => area.state));

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title}>{profile.data.display_name}</Text>
          <Text style={styles.muted}>
            Verification: {verificationStatusLabel(profile.data.verification_status)}
          </Text>
        </View>

        {profile.data.verification_status !== 'APPROVED' ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Waiting on review</Text>
            <Text style={styles.body}>
              Sync reviews every provider before they can enter a customer&apos;s home.
              You can set everything else up in the meantime.
            </Text>
          </View>
        ) : null}

        {gaps.length > 0 ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Before you can receive jobs</Text>
            {gaps.map((gap) => (
              <View key={gap.reason} style={styles.gap}>
                <Text style={styles.body}>{gap.reason}</Text>
                {gap.route !== '/provider' ? (
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => router.push(gap.route as never)}
                  >
                    <Text style={styles.link}>{gap.action}</Text>
                  </Pressable>
                ) : null}
              </View>
            ))}
          </View>
        ) : (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>You are set up for work</Text>
            <Text style={styles.body}>
              Jobs matching your services and areas will appear in your offers.
            </Text>
            <Button label="See offers" variant="secondary" onPress={() => router.push('/offers')} />
          </View>
        )}

        <View style={styles.card}>
          <View style={styles.switchRow}>
            <View style={styles.switchText}>
              <Text style={styles.cardTitle}>Taking work</Text>
              <Text style={styles.muted}>
                Turn this off when you are unavailable. It is separate from approval.
              </Text>
            </View>
            <Switch
              accessibilityLabel="Taking work"
              value={profile.data.is_accepting_jobs}
              disabled={update.isPending}
              onValueChange={(value) => update.mutate({ is_accepting_jobs: value })}
              trackColor={{ true: colors.accent, false: colors.hairline }}
            />
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Services you offer</Text>
          {categories.isPending ? (
            <ActivityIndicator color={colors.accent} />
          ) : (
            (categories.data ?? []).flatMap((category) =>
              category.services.map((service) => {
                const existing = (services.data ?? []).find(
                  (row) => row.service_slug === service.slug,
                );

                return (
                  <Pressable
                    key={service.slug}
                    accessibilityRole="button"
                    accessibilityState={{ selected: listed.has(service.slug) }}
                    accessibilityLabel={service.name}
                    onPress={() =>
                      existing
                        ? removeService.mutate(existing.id)
                        : addService.mutate(service.slug)
                    }
                    style={({ pressed }) => [
                      styles.row,
                      listed.has(service.slug) && styles.rowSelected,
                      pressed && styles.rowPressed,
                    ]}
                  >
                    <Text style={styles.rowTitle}>{service.name}</Text>
                    <Text style={styles.rowMark}>
                      {listed.has(service.slug) ? 'Offering' : 'Add'}
                    </Text>
                  </Pressable>
                );
              }),
            )
          )}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Where you work</Text>
          <Text style={styles.muted}>
            A state means anywhere in it. Tap to add or remove.
          </Text>
          <View style={styles.chips}>
            {NIGERIAN_STATES.map((state) => {
              const existing = (areas.data ?? []).find((area) => area.state === state.value);

              return (
                <Pressable
                  key={state.value}
                  accessibilityRole="button"
                  accessibilityState={{ selected: covered.has(state.value) }}
                  accessibilityLabel={state.label}
                  onPress={() =>
                    existing
                      ? removeArea.mutate(existing.id)
                      : addArea.mutate({ state: state.value })
                  }
                  style={({ pressed }) => [
                    styles.chip,
                    covered.has(state.value) && styles.chipSelected,
                    pressed && styles.chipPressed,
                  ]}
                >
                  <Text
                    style={[
                      styles.chipText,
                      covered.has(state.value) && styles.chipTextSelected,
                    ]}
                  >
                    {state.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <Button
          label="Where you are paid"
          variant="secondary"
          onPress={() => router.push('/payout-destination')}
        />
        <Button label="Back" variant="secondary" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  centred: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.ground,
  },
  content: { padding: spacing.xl, gap: spacing.md },
  header: { gap: spacing.xs, paddingTop: spacing.lg, paddingBottom: spacing.sm },
  title: {
    fontSize: fontSizes.title1,
    fontWeight: fontWeights.bold,
    color: colors.ink,
    letterSpacing: -0.5,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    padding: spacing.lg,
    gap: spacing.md,
  },
  cardError: { borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  link: { fontSize: fontSizes.footnote, fontWeight: fontWeights.semibold, color: colors.accent },
  gap: { gap: spacing.xs },
  section: { gap: spacing.sm, paddingTop: spacing.md },
  sectionTitle: {
    fontSize: fontSizes.callout,
    fontWeight: fontWeights.semibold,
    color: colors.ink,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  switchText: { flexShrink: 1, gap: 2 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    minHeight: 56,
  },
  rowSelected: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  rowPressed: { backgroundColor: colors.surfaceSunk },
  rowTitle: { fontSize: fontSizes.body, fontWeight: fontWeights.medium, color: colors.ink },
  rowMark: { fontSize: fontSizes.footnote, color: colors.inkMuted },
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
