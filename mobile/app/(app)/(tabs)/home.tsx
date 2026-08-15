import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ServiceCategory, ServiceSummary } from '@/api/endpoints/catalog';
import { Icon, categoryIcon } from '@/components/ui/Icon';
import { IconPlate } from '@/components/ui/Pill';
import { ListRow, RowGroup } from '@/components/ui/ListRow';
import { Screen } from '@/components/ui/Screen';
import { SkeletonList } from '@/components/ui/Skeleton';
import { StatusPill } from '@/components/ui/StatusPill';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { useCurrentUser } from '@/features/auth/hooks';
import { useCategories } from '@/features/catalog/hooks';
import { useCustomerActivity } from '@/features/activity/hooks';
import { bookingStatusView } from '@/features/status/presentation';
import { formatPriceFrom } from '@/lib/money';
import { usePalette } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

/**
 * Home: discovery first, and calm.
 *
 * The order is deliberate and it is the whole design of this screen. A greeting
 * establishes who you are, then anything currently happening, then the things
 * you can start. Putting live work above the catalog means a customer waiting
 * on a provider opens the app and sees the answer immediately rather than
 * scrolling past six categories to find it.
 *
 * There is no dashboard here. No statistics, no counts, no cards that exist to
 * fill a grid. Everything on this screen is either something in progress or
 * something you can begin.
 */
export default function HomeScreen() {
  const router = useRouter();
  const palette = usePalette();
  const insets = useSafeAreaInsets();
  const { data: user } = useCurrentUser();
  const categories = useCategories();
  const activity = useCustomerActivity();

  const inFlight = activity.open.slice(0, 2);

  return (
    <Screen
      tabBar
      refreshing={categories.isRefetching}
      onRefresh={() => {
        void categories.refetch();
        void activity.query.refetch();
      }}
      contentContainerStyle={{ paddingTop: insets.top + spacing.sm }}
    >
      <View style={styles.greeting}>
        <Text variant="footnote" tone="muted">
          {greeting()}
        </Text>
        <Text variant="title1" accessibilityRole="header">
          {firstName(user?.first_name, user?.full_name)}
        </Text>
      </View>

      {inFlight.length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="Happening now" />
          <Card padding="none">
            <RowGroup>
              {inFlight.map((booking) => (
                <ListRow
                  key={booking.id}
                  title={booking.service_name}
                  subtitle={booking.provider_name ?? 'Finding you a provider'}
                  icon="clock"
                  iconTone="primary"
                  chevron
                  accessibilityLabel={`${booking.service_name}, ${bookingStatusView(booking.status).label}`}
                  trailing={<StatusPill view={bookingStatusView(booking.status)} />}
                  onPress={() => router.push(`/booking/${booking.id}`)}
                />
              ))}
            </RowGroup>
          </Card>
        </View>
      ) : null}

      <View style={styles.section}>
        <SectionHeader
          title="Book a service"
          action={
            activity.open.length + activity.past.length > 0 ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="See all your activity"
                onPress={() => router.navigate('/activity')}
              >
                <Text variant="caption" tone="primary" weight="semibold">
                  Your activity
                </Text>
              </Pressable>
            ) : undefined
          }
        />

        {categories.isPending ? (
          <SkeletonList rows={3} />
        ) : categories.error ? (
          <ErrorState
            error={categories.error}
            onRetry={() => void categories.refetch()}
            retrying={categories.isRefetching}
          />
        ) : categories.data.length === 0 ? (
          <EmptyState
            icon="briefcase"
            title="Nothing available yet"
            body="Services appear here as soon as they are published."
          />
        ) : (
          <View style={styles.categories}>
            {categories.data.map((category) => (
              <CategoryBlock
                key={category.id}
                category={category}
                onPick={(service) => router.push(`/book/${service.slug}`)}
              />
            ))}
          </View>
        )}
      </View>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Work with Sync as a provider"
        onPress={() => router.push('/provider')}
        style={({ pressed }) => [
          styles.promo,
          { backgroundColor: pressed ? palette.surfaceSunk : palette.surface, borderColor: palette.hairline },
        ]}
      >
        <IconPlate icon="briefcase" tone="primary" size={40} />
        <View style={styles.promoText}>
          <Text variant="body" weight="semibold">
            Work with Sync
          </Text>
          <Text variant="caption" tone="muted">
            Offer a service and get paid for jobs near you
          </Text>
        </View>
        <Icon name="chevronRight" size={18} color={palette.inkMuted} />
      </Pressable>
    </Screen>
  );
}

/**
 * One category and its services.
 *
 * The category is a heading with an icon rather than a card, and the services
 * are rows inside a single card. Wrapping each service in its own card is what
 * turns a catalog into a wall of boxes.
 */
function CategoryBlock({
  category,
  onPick,
}: {
  category: ServiceCategory;
  onPick: (service: ServiceSummary) => void;
}) {
  const palette = usePalette();

  if (category.services.length === 0) return null;

  return (
    <View style={styles.category}>
      <View style={styles.categoryHead}>
        <Icon name={categoryIcon(category.icon_key || category.slug)} size={19} color={palette.primary} />
        <Text variant="title3">{category.name}</Text>
      </View>

      <Card padding="none">
        <RowGroup>
          {category.services.map((service) => (
            <ListRow
              key={service.id}
              title={service.name}
              subtitle={service.summary || undefined}
              chevron
              accessibilityLabel={`${service.name}, ${formatPriceFrom(service.base_price_kobo, service.pricing_model)}`}
              trailing={
                <Text variant="price" tone="primary" numberOfLines={1}>
                  {formatPriceFrom(service.base_price_kobo, service.pricing_model)}
                </Text>
              }
              onPress={() => onPick(service)}
            />
          ))}
        </RowGroup>
      </Card>
    </View>
  );
}

/** Time of day, in the user's own timezone. Small, and it is most of what makes
 *  the screen feel like it is addressed to a person. */
function greeting(now = new Date()): string {
  const hour = now.getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/** Falls back through the names the API might have, then to something neutral.
 *  A screen that opens with "Hello undefined" is worse than one that opens
 *  without a name. */
function firstName(first?: string, full?: string): string {
  const candidate = (first || full || '').trim();
  if (!candidate) return 'Welcome back';
  return candidate.split(/\s+/)[0];
}

const styles = StyleSheet.create({
  greeting: { gap: spacing.xxs },
  section: { gap: spacing.md },
  categories: { gap: spacing.xl },
  category: { gap: spacing.sm },
  categoryHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  promo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radii.card,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  promoText: { flex: 1, gap: spacing.xxs },
});
