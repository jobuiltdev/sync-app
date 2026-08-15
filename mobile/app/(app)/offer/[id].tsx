import { useLocalSearchParams, useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { DetailList, DetailRow, humaniseKey, humaniseValue } from '@/components/ui/DetailList';
import { Header } from '@/components/ui/Header';
import { IconPlate } from '@/components/ui/Pill';
import { Screen } from '@/components/ui/Screen';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusPill } from '@/components/ui/StatusPill';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { ErrorState } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { useAcceptOffer, useDeclineOffer, useOffer } from '@/features/offers/hooks';
import { needsVerification, toOfferOutcome } from '@/features/offers/outcomes';
import { offerStatusView } from '@/features/status/presentation';
import { usePalette } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

/**
 * One job, and the decision on it.
 *
 * Whether the buttons appear is the server's call, carried on `is_actionable`.
 * Deciding locally would mean a provider tapping accept on something the server
 * has already given to somebody else.
 *
 * **A lost race is not an error.** Several providers see the same broadcast, so
 * losing one is the normal working of the market and it is presented as an
 * outcome with a way forward, not as a red failure. A provider who is shown a
 * 409 for doing their job correctly stops trusting the app.
 */
export default function OfferDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const palette = usePalette();

  const { data: offer, isPending, error, refetch } = useOffer(id);
  const accept = useAcceptOffer();
  const decline = useDeclineOffer();

  if (isPending) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <View style={styles.loading}>
          <Skeleton width="60%" height={30} />
          <Skeleton width="100%" height={120} radius={18} />
          <Skeleton width="100%" height={140} radius={18} />
        </View>
      </Screen>
    );
  }

  if (error) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <ErrorState error={error} onRetry={() => void refetch()} />
      </Screen>
    );
  }

  const outcome = toOfferOutcome(accept.error) ?? toOfferOutcome(decline.error);
  const accepted = accept.isSuccess;
  const declined = decline.isSuccess;

  // The offer is over, either because it just resolved or because the server
  // said so. Either way the answer is to go back, not to try again.
  const finished = accepted || declined || outcome?.isFinal || !offer.is_actionable;
  const busy = accept.isPending || decline.isPending;

  return (
    <Screen>
      <Header onBack={() => router.back()} />

      <View style={styles.hero}>
        <Text variant="caption" tone="muted" style={styles.reference}>
          {offer.booking_reference}
        </Text>
        <Text variant="title1" accessibilityRole="header">
          {offer.service_name}
        </Text>
        <StatusPill view={offerStatusView(offer.status)} />
      </View>

      {accepted ? (
        <Card tone="success">
          <View accessibilityRole="alert" style={styles.result}>
            <IconPlate icon="check" tone="success" size={40} />
            <View style={styles.resultText}>
              <Text variant="body" weight="semibold">
                The job is yours
              </Text>
              <Text variant="footnote" tone="soft">
                It is now in your activity, ready to start.
              </Text>
            </View>
          </View>
          <View style={styles.resultAction}>
            <Button label="Go to my work" onPress={() => router.replace('/activity')} />
          </View>
        </Card>
      ) : null}

      {declined ? (
        <Card>
          <View accessibilityRole="alert" style={styles.result}>
            <IconPlate icon="close" tone="neutral" size={40} />
            <View style={styles.resultText}>
              <Text variant="body" weight="semibold">
                Declined
              </Text>
              <Text variant="footnote" tone="soft">
                This job will not appear again. Your acceptance rate is not affected.
              </Text>
            </View>
          </View>
        </Card>
      ) : null}

      {outcome && !accepted && !declined ? (
        // Deliberately not styled as an error when the offer was simply taken.
        // A provider who lost a race did nothing wrong.
        <Card tone={outcome.isFinal ? 'default' : 'danger'}>
          <View accessibilityRole="alert" style={styles.result}>
            <IconPlate
              icon={outcome.isFinal ? 'info' : 'alert'}
              tone={outcome.isFinal ? 'neutral' : 'danger'}
              size={40}
            />
            <View style={styles.resultText}>
              <Text variant="body" weight="semibold">
                {outcome.failure === 'TAKEN'
                  ? 'Somebody else took this one'
                  : outcome.failure === 'EXPIRED'
                    ? 'This offer has lapsed'
                    : 'Could not do that'}
              </Text>
              <Text variant="footnote" tone="soft">
                {outcome.message}
              </Text>
            </View>
          </View>
          {needsVerification(outcome) ? (
            <View style={styles.resultAction}>
              <Button label="Verify my details" onPress={() => router.push('/verify-phone')} />
            </View>
          ) : null}
        </Card>
      ) : null}

      <View style={styles.section}>
        <SectionHeader title="Where" />
        <Card>
          <View style={styles.address}>
            <Text variant="body" weight="medium">
              {offer.street_address}
            </Text>
            {offer.landmark ? (
              <Text variant="footnote" tone="soft">
                {offer.landmark}
              </Text>
            ) : null}
            <Text variant="caption" tone="muted">
              {[offer.area, offer.lga, offer.state].filter(Boolean).join(', ')}
            </Text>
            {offer.directions_note ? (
              <Text variant="caption" tone="muted">
                {offer.directions_note}
              </Text>
            ) : null}
          </View>
        </Card>
      </View>

      {Object.keys(offer.details).length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="What is being asked for" />
          <Card>
            <DetailList>
              {Object.entries(offer.details).map(([key, value]) => (
                <DetailRow key={key} label={humaniseKey(key)} value={humaniseValue(value)} />
              ))}
            </DetailList>
          </Card>
        </View>
      ) : null}

      {offer.is_actionable && !finished ? (
        <Card tone="warning" padding="tight">
          <Text variant="caption" style={{ color: palette.warning }}>
            Offers lapse if nobody answers. Others have been offered this too.
          </Text>
        </Card>
      ) : null}

      <View style={styles.actions}>
        {finished ? (
          <Button label="Back to activity" variant="secondary" onPress={() => router.back()} />
        ) : (
          <>
            <Button
              label="Accept this job"
              icon="check"
              loading={accept.isPending}
              disabled={busy}
              onPress={() => accept.mutate({ id })}
            />
            <Button
              label="Decline"
              variant="ghost"
              loading={decline.isPending}
              disabled={busy}
              onPress={() => decline.mutate({ id })}
            />
          </>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  loading: { gap: spacing.lg },
  hero: { gap: spacing.sm, alignItems: 'flex-start' },
  reference: { fontVariant: ['tabular-nums'] },
  section: { gap: spacing.md },
  result: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  resultText: { flex: 1, gap: spacing.xxs },
  resultAction: { marginTop: spacing.md },
  address: { gap: spacing.xs },
  actions: { gap: spacing.sm },
});
