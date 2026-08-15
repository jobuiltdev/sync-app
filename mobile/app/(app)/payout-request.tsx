import { useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Header } from '@/components/ui/Header';
import { Screen } from '@/components/ui/Screen';
import { Skeleton } from '@/components/ui/Skeleton';
import { Card } from '@/components/ui/Surface';
import { BlockedState, InlineError } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { validateAmount } from '@/features/payments/amount';
import { useEarnings, useRequestPayout } from '@/features/payments/hooks';
import {
  needsDestination,
  needsDestinationVerification,
  needsVerification,
  toPayoutOutcome,
} from '@/features/payments/outcomes';
import { newIdempotencyKey } from '@/lib/idempotency';
import { formatNaira } from '@/lib/money';
import { spacing } from '@/theme/tokens';

/**
 * Asking to be paid.
 *
 * The idempotency key is generated once when the screen mounts and reused for
 * every attempt from it. That is what makes this safe on a Nigerian mobile
 * connection: a request that timed out may well have been received, and without
 * the key a retry would be a second withdrawal.
 *
 * Local validation is a courtesy that saves a doomed round trip. The server
 * decides, and when the two disagree the server is right: another device may
 * have spent the balance since this screen loaded.
 */
export default function PayoutRequestScreen() {
  const router = useRouter();
  const earnings = useEarnings();
  const request = useRequestPayout();

  const [amount, setAmount] = useState('');
  const [idempotencyKey] = useState(newIdempotencyKey);

  const available = earnings.data?.available_kobo ?? 0;
  const { kobo, error: localError } = validateAmount(amount, available);
  const outcome = toPayoutOutcome(request.error);

  const submit = () => {
    if (localError !== null || kobo === null) return;

    request.mutate(
      { amountKobo: kobo, idempotencyKey },
      { onSuccess: (payout) => router.replace(`/payout/${payout.id}`) },
    );
  };

  return (
    <Screen
      footer={
        <Button
          label="Request payout"
          loading={request.isPending}
          disabled={localError !== null || kobo === null}
          onPress={submit}
        />
      }
    >
      <Header onBack={() => router.back()} title="Request a payout" />

      <Card>
        <View style={styles.available}>
          <Text variant="overline" tone="muted">
            Available
          </Text>
          {earnings.isPending ? (
            <Skeleton width="55%" height={38} />
          ) : (
            <Text variant="priceLarge">{formatNaira(available)}</Text>
          )}
        </View>
      </Card>

      <Field
        label="Amount"
        prefix="₦"
        value={amount}
        onChangeText={setAmount}
        keyboardType="number-pad"
        placeholder="0"
        error={amount.length > 0 && localError ? localError : undefined}
        hint={
          kobo !== null && localError === null
            ? `Leaves ${formatNaira(available - kobo)} in your balance.`
            : 'Whole naira only.'
        }
      />

      {outcome ? (
        needsVerification(outcome) ? (
          <BlockedState
            title="Verify your details first"
            body={outcome.message}
            action={<Button label="Verify now" onPress={() => router.push('/verify-phone')} />}
          />
        ) : needsDestination(outcome) ? (
          <BlockedState
            icon="bank"
            title="No bank account on file"
            body={outcome.message}
            action={
              <Button
                label="Add your account"
                onPress={() => router.push('/payout-destination')}
              />
            }
          />
        ) : needsDestinationVerification(outcome) ? (
          <BlockedState
            icon="bank"
            title="Confirm your account first"
            body={outcome.message}
            action={
              <Button
                label="Confirm with your bank"
                onPress={() => router.push('/payout-destination')}
              />
            }
          />
        ) : (
          <InlineError error={request.error} />
        )
      ) : null}

      <Text variant="caption" tone="muted">
        Payouts go only to the account you have confirmed with your bank. Sync never
        sends the same transfer twice.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  available: { gap: spacing.xs },
});
