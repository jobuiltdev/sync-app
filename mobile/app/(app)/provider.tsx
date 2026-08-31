import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Switch, View } from 'react-native';

import { eligibilityGaps } from '@/api/endpoints/providers';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Header } from '@/components/ui/Header';
import { Icon } from '@/components/ui/Icon';
import { IconPlate, Pill } from '@/components/ui/Pill';
import { ListRow, RowGroup } from '@/components/ui/ListRow';
import { Screen } from '@/components/ui/Screen';
import { Sheet } from '@/components/ui/Sheet';
import { Skeleton, SkeletonList } from '@/components/ui/Skeleton';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { ErrorState, InlineError } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
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
import { verificationStatusView } from '@/features/status/presentation';
import type { VerificationStatus } from '@/api/endpoints/providers';
import { NIGERIAN_STATES, stateLabel } from '@/lib/nigeria';
import { usePalette } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

/**
 * The provider workspace.
 *
 * A workspace, not an admin dashboard: the difference is that this screen is
 * organised around the three questions a provider actually has, in order. Am I
 * approved. Am I set up to receive work. What am I offering and where.
 *
 * Everything here reflects server state. **Approval is adjudicated and never
 * self-declared**: the API refuses to accept a verification status, so this
 * screen shows the one it was given and offers no control that would change it.
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

  const palette = usePalette();
  const [displayName, setDisplayName] = useState('');
  const [bio, setBio] = useState('');
  const [pickingServices, setPickingServices] = useState(false);
  const [pickingAreas, setPickingAreas] = useState(false);

  if (profile.isPending) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <View style={styles.loading}>
          <Skeleton width="60%" height={30} />
          <Skeleton width="100%" height={110} radius={18} />
          <Skeleton width="100%" height={140} radius={18} />
        </View>
      </Screen>
    );
  }

  // No profile is an ordinary state, not an error: most accounts are customers.
  if (!profile.data) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />

        <View style={styles.onboard}>
          <IconPlate icon="briefcase" tone="primary" size={56} />
          <View style={styles.onboardText}>
            <Text variant="title1" accessibilityRole="header">
              Work with Sync
            </Text>
            <Text variant="body" tone="muted">
              Take jobs from customers near you. Your account stays the same; this adds the
              provider side of it.
            </Text>
          </View>
        </View>

        <View style={styles.form}>
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

          <InlineError error={create.error} />

          <Button
            label="Create provider profile"
            loading={create.isPending}
            disabled={displayName.trim().length === 0}
            onPress={() => create.mutate({ display_name: displayName.trim(), bio: bio.trim() })}
          />
        </View>

        <Text variant="caption" tone="muted">
          Sync reviews every provider before they can enter a customer&apos;s home. You can set
          up your services and areas while that happens.
        </Text>
      </Screen>
    );
  }

  const status = verificationStatusView(profile.data.verification_status);
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
    <Screen refreshing={profile.isRefetching} onRefresh={() => void profile.refetch()}>
      <Header onBack={() => router.back()} />

      <View style={styles.hero}>
        <Text variant="title1" accessibilityRole="header">
          {profile.data.display_name}
        </Text>
        <Pill label={status.label} tone={status.tone} dot={status.live} />
        {status.detail ? (
          <Text variant="footnote" tone="soft">
            {status.detail}
          </Text>
        ) : null}
      </View>

      {/* Verification, which is the one part of readiness a provider acts on
          somewhere else. Shown before the gap list because it is the first gate,
          and because a provider halfway through a check should be able to get
          back to it without hunting. */}
      <RowGroup>
        <ListRow
          title="Provider verification"
          subtitle={verificationRowSubtitle(profile.data.verification_status)}
          icon="shield"
          iconTone={profile.data.verification_status === 'APPROVED' ? 'success' : 'primary'}
          onPress={() => router.push('/provider-verification')}
          chevron
        />
      </RowGroup>

      {/* Readiness, stated plainly. A provider's first question is always
          "why am I not getting jobs", and this answers it before it is asked. */}
      {gaps.length > 0 ? (
        <Card tone="warning">
          <View style={styles.gaps}>
            <Text variant="body" weight="semibold">
              Before you can receive jobs
            </Text>
            {gaps.map((gap) => (
              <View key={gap.reason} style={styles.gap}>
                <Icon name="alert" size={16} color={palette.warning} />
                <View style={styles.gapText}>
                  <Text variant="footnote" tone="soft">
                    {gap.reason}
                  </Text>
                  {gap.route !== '/provider' ? (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={gap.action}
                      onPress={() => router.push(gap.route as never)}
                    >
                      <Text variant="caption" tone="primary" weight="semibold">
                        {gap.action}
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
              </View>
            ))}
          </View>
        </Card>
      ) : (
        <Card tone="success">
          <View style={styles.ready}>
            <IconPlate icon="check" tone="success" size={40} />
            <View style={styles.readyText}>
              <Text variant="body" weight="semibold">
                You are set up for work
              </Text>
              <Text variant="footnote" tone="soft">
                Jobs matching your services and areas appear in your activity.
              </Text>
            </View>
          </View>
        </Card>
      )}

      <Card>
        <View style={styles.switchRow}>
          <View style={styles.switchText}>
            <Text variant="body" weight="semibold">
              Taking work
            </Text>
            <Text variant="caption" tone="muted">
              Turn this off when you are unavailable. It is separate from approval.
            </Text>
          </View>
          <Switch
            accessibilityLabel="Taking work"
            value={profile.data.is_accepting_jobs}
            disabled={update.isPending}
            onValueChange={(value) => update.mutate({ is_accepting_jobs: value })}
            trackColor={{ true: palette.primary, false: palette.hairline }}
            thumbColor={palette.surface}
          />
        </View>
      </Card>

      <InlineError error={update.error ?? addService.error ?? addArea.error} />

      <View style={styles.section}>
        <SectionHeader
          title="Services you offer"
          action={
            <Pressable accessibilityRole="button" onPress={() => setPickingServices(true)}>
              <Text variant="caption" tone="primary" weight="semibold">
                Edit
              </Text>
            </Pressable>
          }
        />
        {services.isPending ? (
          <SkeletonList rows={2} showPlate={false} />
        ) : listed.size === 0 ? (
          <Card>
            <Text variant="footnote" tone="muted">
              You have not listed any services yet. Nothing will be offered to you until you do.
            </Text>
          </Card>
        ) : (
          <Card padding="none">
            <RowGroup>
              {(services.data ?? []).map((service) => (
                <ListRow
                  key={service.id}
                  title={service.service_name}
                  subtitle={service.is_active ? undefined : 'Not active'}
                  icon="briefcase"
                  trailing={
                    <Button
                      label="Remove"
                      variant="ghost"
                      size="compact"
                      fullWidth={false}
                      onPress={() => removeService.mutate(service.id)}
                    />
                  }
                />
              ))}
            </RowGroup>
          </Card>
        )}
      </View>

      <View style={styles.section}>
        <SectionHeader
          title="Where you work"
          action={
            <Pressable accessibilityRole="button" onPress={() => setPickingAreas(true)}>
              <Text variant="caption" tone="primary" weight="semibold">
                Edit
              </Text>
            </Pressable>
          }
        />
        {covered.size === 0 ? (
          <Card>
            <Text variant="footnote" tone="muted">
              You have not said where you work. Add at least one state.
            </Text>
          </Card>
        ) : (
          <View style={styles.chips}>
            {(areas.data ?? []).map((area) => (
              <View
                key={area.id}
                style={[
                  styles.areaChip,
                  { backgroundColor: palette.primarySoft, borderColor: palette.primarySoft },
                ]}
              >
                <Text variant="footnote" weight="medium" style={{ color: palette.onPrimarySoft }}>
                  {stateLabel(area.state)}
                </Text>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`Remove ${stateLabel(area.state)}`}
                  hitSlop={8}
                  onPress={() => removeArea.mutate(area.id)}
                >
                  <Icon name="close" size={14} color={palette.onPrimarySoft} strokeWidth={2.2} />
                </Pressable>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* --- pickers -------------------------------------------------------- */}

      <Sheet
        visible={pickingServices}
        onClose={() => setPickingServices(false)}
        title="Services you offer"
        subtitle="Tap to add or remove. You are only offered jobs for services on this list."
      >
        {categories.isPending ? (
          <SkeletonList rows={4} showPlate={false} />
        ) : categories.error ? (
          <ErrorState error={categories.error} onRetry={() => void categories.refetch()} />
        ) : (
          (categories.data ?? []).flatMap((category) =>
            category.services.map((service) => {
              const existing = (services.data ?? []).find(
                (row) => row.service_slug === service.slug,
              );
              const on = listed.has(service.slug);

              return (
                <ListRow
                  key={service.slug}
                  title={service.name}
                  subtitle={category.name}
                  accessibilityLabel={`${service.name}, ${on ? 'offering' : 'not offering'}`}
                  onPress={() =>
                    existing ? removeService.mutate(existing.id) : addService.mutate(service.slug)
                  }
                  trailing={
                    on ? (
                      <Icon name="check" size={19} color={palette.primary} strokeWidth={2.4} />
                    ) : (
                      <Icon name="plus" size={19} color={palette.inkMuted} />
                    )
                  }
                />
              );
            }),
          )
        )}
      </Sheet>

      <Sheet
        visible={pickingAreas}
        onClose={() => setPickingAreas(false)}
        title="Where you work"
        subtitle="A state means anywhere in it."
      >
        {NIGERIAN_STATES.map((state) => {
          const existing = (areas.data ?? []).find((area) => area.state === state.value);

          return (
            <ListRow
              key={state.value}
              title={state.label}
              accessibilityLabel={`${state.label}, ${existing ? 'covered' : 'not covered'}`}
              onPress={() =>
                existing ? removeArea.mutate(existing.id) : addArea.mutate({ state: state.value })
              }
              trailing={
                existing ? (
                  <Icon name="check" size={19} color={palette.primary} strokeWidth={2.4} />
                ) : (
                  <Icon name="plus" size={19} color={palette.inkMuted} />
                )
              }
            />
          );
        })}
      </Sheet>
    </Screen>
  );
}

/**
 * One line telling a provider where their approval stands.
 *
 * Deliberately not the same wording as the status pill above it. The pill names
 * the state; this says what it means for them.
 *
 * It describes **approval standing only**, because that is the only thing this
 * screen knows. `verification_status` is the profile lifecycle: it says a person
 * decided, not which checks ran. An account approved before identity
 * verification existed carries APPROVED with no NIN, face or liveness check
 * behind it, so wording like "verified" or "your checks passed" here would be
 * asserting something no query on this screen has established. The detail screen
 * loads the attempt and can be specific; this row cannot.
 */
function verificationRowSubtitle(status: VerificationStatus): string {
  switch (status) {
    case 'APPROVED':
      return 'Approved by the Sync team. You can take work.';
    case 'UNDER_REVIEW':
      return 'With the Sync team. Someone is reviewing it.';
    case 'REJECTED':
      return 'Not approved. Read why and submit again.';
    case 'SUSPENDED':
      return 'Suspended. Contact support.';
    default:
      return 'Not approved yet. Confirm your identity to take work.';
  }
}

const styles = StyleSheet.create({
  loading: { gap: spacing.lg },
  hero: { gap: spacing.sm, alignItems: 'flex-start' },
  onboard: { alignItems: 'flex-start', gap: spacing.lg },
  onboardText: { gap: spacing.xs },
  form: { gap: spacing.lg },
  section: { gap: spacing.md },
  gaps: { gap: spacing.md },
  gap: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
  gapText: { flex: 1, gap: spacing.xxs },
  ready: { flexDirection: 'row', gap: spacing.md, alignItems: 'center' },
  readyText: { flex: 1, gap: spacing.xxs },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  switchText: { flex: 1, gap: spacing.xxs },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  areaChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radii.pill,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
});