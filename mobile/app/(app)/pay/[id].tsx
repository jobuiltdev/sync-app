import * as Linking from 'expo-linking';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { paymentStatusLabel } from '@/api/endpoints/payments-customer';
import { Button } from '@/components/ui/Button';
import { useBooking } from '@/features/bookings/hooks';
import { type CheckoutStage, stageLabel, toPaymentOutcome } from '@/features/payments/checkout';
import { useStartPayment, useVerifyPayment } from '@/features/payments/hooks';
import { newIdempotencyKey } from '@/lib/idempotency';
import { formatNaira } from '@/lib/money';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Paying for a booking.
 *
 * Three steps, and the app is only in charge of the first. It asks the server to
 * start a payment, opens the provider's hosted checkout in the system browser,
 * and when the customer comes back it asks the server to check. It never decides
 * that a payment succeeded: coming back from the browser proves nothing, since a
 * customer who closed the page and one who paid look identical from here.
 *
 * Card details never touch this app, which is why checkout is a hosted page
 * rather than a form. It also means no native module and no new dependency, so
 * the project stays on Expo SDK 54 and keeps working in Expo Go.
 */
export default function PayScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const booking = useBooking(id);
  const start = useStartPayment();
  const verify = useVerifyPayment();

  const [idempotencyKey] = useState(newIdempotencyKey);
  const [stage, setStage] = useState<CheckoutStage>('IDLE');

  const payment = verify.data ?? start.data ?? null;
  const outcome = toPaymentOutcome(start.error ?? verify.error);

  const openCheckout = () => {
    setStage('STARTING');

    start.mutate(
      { bookingId: id, idempotencyKey },
      {
        onSuccess: async (intent) => {
          if (intent.status === 'SUCCESSFUL') {
            setStage('PAID');
            return;
          }

          setStage('AWAITING_PAYMENT');
          if (intent.authorization_url) {
            await Linking.openURL(intent.authorization_url);
          }
        },
        onError: () => setStage('IDLE'),
      },
    );
  };

  const check = () => {
    if (!payment) return;

    setStage('CHECKING');
    verify.mutate(payment.id, {
      onSuccess: (intent) => {
        setStage(
          intent.status === 'SUCCESSFUL'
            ? 'PAID'
            : intent.status === 'FAILED'
              ? 'FAILED'
              : 'AWAITING_PAYMENT',
        );
      },
      onError: () => setStage('AWAITING_PAYMENT'),
    });
  };

  if (booking.isPending) {
    return (
      <SafeAreaView style={styles.centred}>
        <ActivityIndicator color={colors.accent} />
      </SafeAreaView>
    );
  }

  if (booking.error) {
    return (
      <SafeAreaView style={styles.centred}>
        <Text style={styles.body}>{booking.error.message}</Text>
        <Button label="Back" variant="secondary" onPress={() => router.back()} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.reference}>{booking.data.reference}</Text>
          <Text style={styles.title}>{booking.data.service_name}</Text>
        </View>

        <View style={styles.amountCard}>
          <Text style={styles.amountLabel}>Amount to pay</Text>
          <Text
            accessibilityLabel={`Amount to pay, ${formatNaira(booking.data.total_kobo)}`}
            style={styles.amount}
          >
            {formatNaira(booking.data.total_kobo)}
          </Text>
          <Text style={styles.muted}>
            The price agreed when you made this booking. It does not change.
          </Text>
        </View>

        {stage !== 'IDLE' ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{stageLabel(stage)}</Text>
            {payment ? (
              <Text style={styles.muted}>
                {paymentStatusLabel(payment.status)}
                {payment.method ? ` by ${payment.method.replace(/_/g, ' ')}` : ''}
              </Text>
            ) : null}
            {start.isPending || verify.isPending ? (
              <ActivityIndicator color={colors.accent} />
            ) : null}
          </View>
        ) : null}

        {outcome ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not take that payment</Text>
            <Text style={styles.body}>{outcome.message}</Text>
            {outcome.isRetryable ? (
              <Button label="Try again" variant="secondary" onPress={openCheckout} />
            ) : null}
          </View>
        ) : null}

        {stage === 'PAID' ? (
          <>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Payment received</Text>
              <Text style={styles.body}>
                Thank you. Your provider will be paid once the work is confirmed.
              </Text>
            </View>
            <Button label="Back to booking" onPress={() => router.back()} />
          </>
        ) : stage === 'AWAITING_PAYMENT' || stage === 'FAILED' || stage === 'CHECKING' ? (
          <>
            <Button
              label="I have paid, check now"
              loading={verify.isPending}
              onPress={check}
            />
            <Button label="Open checkout again" variant="secondary" onPress={openCheckout} />
          </>
        ) : (
          <Button label="Pay now" loading={start.isPending} onPress={openCheckout} />
        )}

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
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.ground,
  },
  content: { padding: spacing.xl, gap: spacing.md },
  header: { gap: spacing.xs, paddingTop: spacing.lg, paddingBottom: spacing.sm },
  reference: { fontSize: fontSizes.caption, color: colors.inkMuted, fontVariant: ['tabular-nums'] },
  title: {
    fontSize: fontSizes.title2,
    fontWeight: fontWeights.bold,
    color: colors.ink,
    letterSpacing: -0.5,
  },
  amountCard: {
    backgroundColor: colors.accentSoft,
    borderRadius: radii.card,
    padding: spacing.xl,
    gap: spacing.xs,
  },
  amountLabel: { fontSize: fontSizes.footnote, color: colors.inkSoft },
  amount: {
    fontSize: fontSizes.title1,
    fontWeight: fontWeights.bold,
    color: colors.accent,
    fontVariant: ['tabular-nums'],
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
});
