import { useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { BookingSummary } from '@/api/endpoints/bookings';
import type { OfferSummary } from '@/api/endpoints/offers';
import { ListRow, RowGroup } from '@/components/ui/ListRow';
import { Screen } from '@/components/ui/Screen';
import { Segmented } from '@/components/ui/Segmented';
import { SkeletonList } from '@/components/ui/Skeleton';
import { StatusPill } from '@/components/ui/StatusPill';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import {
  type ActivityScope,
  useCustomerActivity,
  useIsProvider,
  useProviderActivity,
} from '@/features/activity/hooks';
import {
  bookingStatusView,
  jobStatusView,
  offerStatusView,
} from '@/features/status/presentation';
import { formatNaira } from '@/lib/money';
import { spacing } from '@/theme/tokens';

/**
 * Activity: everything in motion, from whichever side you are on.
 *
 * One screen replaced three. The segmented control appears only for accounts
 * that actually have a provider side, so a customer never sees a control with
 * one option, and a provider is never forced into a second navigation system.
 */
export default function ActivityScreen() {
  const insets = useSafeAreaInsets();
  const isProvider = useIsProvider();
  const [scope, setScope] = useState<ActivityScope>('customer');

  const showing: ActivityScope = isProvider ? scope : 'customer';

  return (
    <Screen tabBar contentContainerStyle={{ paddingTop: insets.top + spacing.sm }}>
      <View style={styles.head}>
        <Text variant="title1" accessibilityRole="header">
          Activity
        </Text>
        {isProvider ? (
          <Segmented
            accessibilityLabel="Which activity to show"
            segments={[
              { value: 'customer', label: 'Your bookings' },
              { value: 'provider', label: 'Your work' },
            ]}
            value={showing}
            onChange={setScope}
          />
        ) : null}
      </View>

      {showing === 'customer' ? <CustomerActivity /> : <ProviderActivity />}
    </Screen>
  );
}

function CustomerActivity() {
  const router = useRouter();
  const { query, open, past } = useCustomerActivity();

  if (query.isPending) return <SkeletonList rows={3} />;
  if (query.error) {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        retrying={query.isRefetching}
      />
    );
  }

  if (open.length === 0 && past.length === 0) {
    return (
      <EmptyState
        icon="clock"
        title="Nothing booked yet"
        body="When you request a service it will show up here, with its progress."
      />
    );
  }

  return (
    <>
      {open.length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="In progress" />
          <Card padding="none">
            <RowGroup>
              {open.map((booking) => (
                <BookingRow
                  key={booking.id}
                  booking={booking}
                  onPress={() => router.push(`/booking/${booking.id}`)}
                />
              ))}
            </RowGroup>
          </Card>
        </View>
      ) : null}

      {past.length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="Past" />
          <Card padding="none">
            <RowGroup>
              {past.map((booking) => (
                <BookingRow
                  key={booking.id}
                  booking={booking}
                  onPress={() => router.push(`/booking/${booking.id}`)}
                />
              ))}
            </RowGroup>
          </Card>
        </View>
      ) : null}
    </>
  );
}

function ProviderActivity() {
  const router = useRouter();
  const { jobsQuery, offersQuery, offers, active, past } = useProviderActivity();

  if (jobsQuery.isPending || offersQuery.isPending) return <SkeletonList rows={3} />;

  const error = jobsQuery.error ?? offersQuery.error;
  if (error) {
    return (
      <ErrorState
        error={error}
        onRetry={() => {
          void jobsQuery.refetch();
          void offersQuery.refetch();
        }}
        retrying={jobsQuery.isRefetching || offersQuery.isRefetching}
      />
    );
  }

  if (offers.length === 0 && active.length === 0 && past.length === 0) {
    return (
      <EmptyState
        icon="briefcase"
        title="No work yet"
        body="Job offers near you appear here. Check your provider profile if you are not receiving any."
      />
    );
  }

  return (
    <>
      {offers.length > 0 ? (
        <View style={styles.section}>
          {/* Offers first and always. They expire, and everything else on this
              screen will still be here in an hour. */}
          <SectionHeader title="Offered to you" />
          <Card padding="none">
            <RowGroup>
              {offers.map((offer) => (
                <OfferRow
                  key={offer.id}
                  offer={offer}
                  onPress={() => router.push(`/offer/${offer.id}`)}
                />
              ))}
            </RowGroup>
          </Card>
        </View>
      ) : null}

      {active.length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="Your jobs" />
          <Card padding="none">
            <RowGroup>
              {active.map((job) => (
                <JobRow key={job.id} job={job} onPress={() => router.push(`/job/${job.id}`)} />
              ))}
            </RowGroup>
          </Card>
        </View>
      ) : null}

      {past.length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="Finished" />
          <Card padding="none">
            <RowGroup>
              {past.map((job) => (
                <JobRow key={job.id} job={job} onPress={() => router.push(`/job/${job.id}`)} />
              ))}
            </RowGroup>
          </Card>
        </View>
      ) : null}
    </>
  );
}

function BookingRow({ booking, onPress }: { booking: BookingSummary; onPress: () => void }) {
  const view = bookingStatusView(booking.status);

  return (
    <ListRow
      title={booking.service_name}
      subtitle={booking.provider_name ?? undefined}
      meta={booking.address_summary}
      chevron
      accessibilityLabel={`${booking.service_name}, ${view.label}, ${formatNaira(booking.total_kobo)}`}
      trailing={
        <View style={styles.trailing}>
          <StatusPill view={view} />
          <Text variant="caption" tone="muted">
            {formatNaira(booking.total_kobo)}
          </Text>
        </View>
      }
      onPress={onPress}
    />
  );
}

function JobRow({ job, onPress }: { job: BookingSummary; onPress: () => void }) {
  const view = jobStatusView(job.status);

  return (
    <ListRow
      title={job.service_name}
      subtitle={job.address_summary}
      chevron
      accessibilityLabel={`${job.service_name}, ${view.label}`}
      trailing={
        <View style={styles.trailing}>
          <StatusPill view={view} />
          <Text variant="caption" tone="muted">
            {formatNaira(job.total_kobo)}
          </Text>
        </View>
      }
      onPress={onPress}
    />
  );
}

function OfferRow({ offer, onPress }: { offer: OfferSummary; onPress: () => void }) {
  return (
    <ListRow
      title={offer.service_name}
      // Area and state only. The street address is not in the offer payload and
      // is not the app's to reveal before the job is accepted.
      subtitle={[offer.area, offer.state].filter(Boolean).join(', ')}
      chevron
      accessibilityLabel={`${offer.service_name} in ${offer.area || offer.state}, awaiting your answer`}
      trailing={<StatusPill view={offerStatusView(offer.status)} />}
      onPress={onPress}
    />
  );
}

const styles = StyleSheet.create({
  head: { gap: spacing.lg },
  section: { gap: spacing.md },
  trailing: { alignItems: 'flex-end', gap: spacing.xs },
});
