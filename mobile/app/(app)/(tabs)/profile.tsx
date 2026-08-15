import { useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Avatar } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { ListRow, RowGroup } from '@/components/ui/ListRow';
import { Pill } from '@/components/ui/Pill';
import { Screen } from '@/components/ui/Screen';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { Text } from '@/components/ui/Text';
import { useCurrentUser, useSignOut } from '@/features/auth/hooks';
import { useProviderProfile } from '@/features/providers/hooks';
import { verificationStatusView } from '@/features/status/presentation';
import { THEME_MODE_LABELS, useTheme } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

/**
 * Profile: the account and everything that is not a daily destination.
 *
 * Grouped rather than listed. Fourteen rows in one column is a settings screen
 * from 2011; the same fourteen in four labelled groups is navigable at a
 * glance. The provider group is absent entirely for accounts without a provider
 * side, replaced by a single invitation, so a customer is never shown the
 * controls of a role they do not have.
 */
export default function ProfileScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data: user } = useCurrentUser();
  const provider = useProviderProfile();
  const signOut = useSignOut();
  const { mode } = useTheme();

  const isProvider = Boolean(provider.data);
  const unverified = user ? !user.is_phone_verified || !user.is_email_verified : false;

  return (
    <Screen tabBar contentContainerStyle={{ paddingTop: insets.top + spacing.sm }}>
      <View style={styles.identity}>
        <Avatar name={user?.full_name || user?.email || '?'} size={64} />
        <View style={styles.identityText}>
          <Text variant="title2" numberOfLines={1}>
            {user?.full_name?.trim() || 'Your account'}
          </Text>
          <Text variant="footnote" tone="muted" numberOfLines={1}>
            {user?.email ?? ''}
          </Text>
        </View>
      </View>

      <View style={styles.section}>
        <SectionHeader title="Account" />
        <Card padding="none">
          <RowGroup>
            <ListRow
              title="Phone and email"
              subtitle={
                unverified ? 'Verify to book and to take work' : 'Both verified'
              }
              icon="shield"
              iconTone={unverified ? 'warning' : 'success'}
              chevron
              trailing={
                unverified ? <Pill label="Action needed" tone="warning" dot /> : undefined
              }
              onPress={() => router.push('/verify-phone')}
            />
            <ListRow
              title="Addresses"
              subtitle="Where your bookings happen"
              icon="pin"
              chevron
              onPress={() => router.push('/addresses')}
            />
          </RowGroup>
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title="Working with Sync" />
        <Card padding="none">
          {isProvider ? (
            <RowGroup>
              <ListRow
                title="Provider profile"
                subtitle="Services, areas and availability"
                icon="briefcase"
                chevron
                trailing={
                  provider.data ? (
                    <Pill
                      label={verificationStatusView(provider.data.verification_status).label}
                      tone={verificationStatusView(provider.data.verification_status).tone}
                      dot={verificationStatusView(provider.data.verification_status).live}
                    />
                  ) : undefined
                }
                onPress={() => router.push('/provider')}
              />
              <ListRow
                title="Earnings"
                subtitle="What you have made and what is available"
                icon="wallet"
                chevron
                onPress={() => router.push('/earnings')}
              />
              <ListRow
                title="Payouts"
                subtitle="Money sent to your bank"
                icon="bank"
                chevron
                onPress={() => router.push('/payouts')}
              />
              <ListRow
                title="Payout destination"
                subtitle="The account we pay into"
                icon="card"
                chevron
                onPress={() => router.push('/payout-destination')}
              />
            </RowGroup>
          ) : (
            <ListRow
              title="Become a provider"
              subtitle="Offer a service and get paid for jobs near you"
              icon="briefcase"
              iconTone="primary"
              chevron
              onPress={() => router.push('/provider')}
            />
          )}
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title="App" />
        <Card padding="none">
          <RowGroup>
            <ListRow
              title="Appearance"
              subtitle="Light, dark, or follow your device"
              icon={mode === 'dark' ? 'moon' : mode === 'light' ? 'sun' : 'device'}
              chevron
              trailing={
                <Text variant="footnote" tone="muted">
                  {THEME_MODE_LABELS[mode]}
                </Text>
              }
              onPress={() => router.push('/appearance')}
            />
            <ListRow
              title="Notifications"
              // Honest rather than aspirational. Sync sends SMS and email from
              // the server; there is no device push and no in-app inbox, and
              // inventing a screen for either would be inventing a feature.
              subtitle="Sent by SMS and email to your verified details"
              icon="bell"
              chevron
              onPress={() => router.push('/verify-phone')}
            />
          </RowGroup>
        </Card>
      </View>

      <Button
        label="Sign out"
        variant="ghost"
        icon="logout"
        loading={signOut.isPending}
        onPress={() => signOut.mutate()}
      />

      <Text variant="caption" tone="muted" center>
        Sync
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  identity: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  identityText: { flex: 1, gap: spacing.xxs },
  section: { gap: spacing.md },
});
