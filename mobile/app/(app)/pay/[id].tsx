import * as Linking from 'expo-linking';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { Header } from '@/components/ui/Header';
import { IconPlate } from '@/components/ui/Pill';
import { Screen } from '@/components/ui/Screen';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusPill } from '@/components/ui/StatusPill';
import { Card } from '@/components/ui/Surface';
import { ErrorState, InlineError } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { useBooking } from '@/features/bookings/hooks';
import { type CheckoutStage, stageLabel, toPaymentOutcome } from '@/features/payments/checkout';
import { useStartPayment, useVerifyPayment } from '@/features/payments/hooks';
import { paymentStatusView } from '@/features/status/presentation';
import { newIdempotencyKey } from '@/lib/idempotency';
import { formatNaira } from '@/lib/money';
import { spacing } from '@/theme/tokens';

/**
 * Paying for a booking.
 *
 * Three steps, and the app is only in charge of the first. It asks the server to
 * start a payment, opens the provider's hosted checkout in the system browser,
 * and when the customer comes back it asks the server to check.
 *
 * **It never decides that a payment succeeded.** Coming back from the browser
 * proves nothing: a customer who paid and one who closed the page look identical
 * from here. Nothing on this screen says "paid" until the server, having asked
 * the payment provider, says so. That is why returning from checkout puts the
 * screen in "check payment" and not in a success state.
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
      <Screen>
        <Header onBack={() => router.back()} />
        <View style={styles.loading}>
          <Skeleton width="50%" height={28} />
          <Skeleton width="100%" height={160} radius={18} />
        </View>
      </Screen>
    );
  }

  if (booking.error) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <ErrorState error={booking.error} onRetry={() => void booking.refetch()} />
      </Screen>
    );
  }

  const paid = stage === 'PAID';
  const busy = start.isPending || verify.isPending;

  return (
    <Screen>
      <Header onBack={() => router.back()} />

      <View style={styles.head}>
        <Text variant="caption" tone="muted" style={styles.reference}>
          {booking.data.reference}
        </Text>
        <Text variant="title1" accessibilityRole="header">
          {paid ? 'Payment received' : 'Pay for this booking'}
        </Text>
        <Text variant="footnote" tone="muted">
          {booking.data.service_name}
        </Text>
      </View>

      <Card tone={paid ? 'success' : 'default'}>
        <View style={styles.amount}>
          {paid ? <IconPlate icon="check" tone="success" size={44} /> : null}
          <Text variant="overline" tone="muted">
            {paid ? 'Amount paid' : 'Amount to pay'}
          </Text>
          <Text
            variant="priceLarge"
            accessibilityLabel={`${paid ? 'Amount paid' : 'Amount to pay'}, ${formatNaira(booking.data.total_kobo)}`}
          >
            {formatNaira(booking.data.total_kobo)}
          </Text>
          <Text variant="caption" tone="muted">
            The price agreed when you made this booking. It does not change.
          </Text>
        </View>
      </Card>

      {stage !== 'IDLE' ? (
        <Card>
          <View style={styles.stage}>
            <Text variant="body" weight="semibold">
              {stageLabel(stage)}
            </Text>
            {payment ? <StatusPill view={paymentStatusView(payment.status)} /> : null}
            {payment?.method ? (
              <Text variant="caption" tone="muted">
                Paid by {payment.method.replace(/_/g, ' ').toLowerCase()}
              </Text>
            ) : null}
            {stage === 'AWAITING_PAYMENT' ? (
              <Text variant="caption" tone="muted">
                We will not mark this paid until your bank confirms it with us.
              </Text>
            ) : null}
          </View>
        </Card>
      ) : null}

      {outcome ? <InlineError error={start.error ?? verify.error} /> : null}

      <View style={styles.actions}>
        {paid ? (
          <Button
            label="Back to booking"
            onPress={() => router.replace(`/booking/${id}`)}
          />
        ) : stage === 'AWAITING_PAYMENT' || stage === 'FAILED' || stage === 'CHECKING' ? (
          <>
            <Button
              label="I have paid, check now"
              icon="refresh"
              loading={verify.isPending}
              disabled={busy}
              onPress={check}
            />
            <Button
              label="Open checkout again"
              variant="secondary"
              disabled={busy}
              onPress={openCheckout}
            />
          </>
        ) : (
          <Button
            label="Pay now"
            icon="card"
            loading={start.isPending}
            disabled={busy}
            onPress={openCheckout}
          />
        )}
      </View>

      <Text variant="caption" tone="muted" center>
        Payment opens in your browser. Your card details never reach this app.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  loading: { gap: spacing.lg },
  head: { gap: spacing.xs },
  reference: { fontVariant: ['tabular-nums'] },
  amount: { gap: spacing.xs, alignItems: 'flex-start' },
  stage: { gap: spacing.sm, alignItems: 'flex-start' },
  actions: { gap: spacing.sm },
});
