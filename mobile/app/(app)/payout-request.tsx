import { useRouter } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
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
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Asking to be paid.
 *
 * The amount is entered in naira and converted to kobo once, here, on the way
 * out. Everything that crosses the API is an integer number of kobo, so there is
 * no point at which a fraction of a naira can be introduced.
 *
 * The idempotency key is minted once when the screen opens and held for the life
 * of this attempt. A tap that times out and is tapped again sends the same key,
 * so the server answers with the payout it already made rather than making a
 * second one.
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
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title}>Request a payout</Text>
          {earnings.isPending ? (
            <ActivityIndicator color={colors.accent} />
          ) : (
            <Text style={styles.muted}>{formatNaira(available)} available</Text>
          )}
        </View>

        <Field
          label="Amount in naira"
          value={amount}
          onChangeText={setAmount}
          keyboardType="number-pad"
          placeholder="0"
          error={amount.length > 0 && localError ? localError : undefined}
        />

        {kobo !== null && localError === null ? (
          <Text style={styles.muted}>
            You will be sent {formatNaira(kobo)}, leaving {formatNaira(available - kobo)}.
          </Text>
        ) : null}

        {outcome ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>{headline(outcome.failure)}</Text>
            <Text style={styles.body}>{outcome.message}</Text>

            {needsVerification(outcome) ? (
              <Button
                label="Verify now"
                variant="secondary"
                onPress={() => router.push('/verify-phone')}
              />
            ) : null}

            {needsDestination(outcome) ? (
              <Button
                label="Add your bank account"
                variant="secondary"
                onPress={() => router.push('/payout-destination')}
              />
            ) : null}

            {needsDestinationVerification(outcome) ? (
              <Button
                label="Confirm your bank account"
                variant="secondary"
                onPress={() => router.push('/payout-destination')}
              />
            ) : null}

            {outcome.isRetryable ? (
              <Button label="Try again" variant="secondary" onPress={submit} />
            ) : null}
          </View>
        ) : null}

        <Button
          label="Request payout"
          loading={request.isPending}
          disabled={localError !== null}
          onPress={submit}
        />
        <Button label="Back" variant="secondary" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

function headline(failure: string): string {
  switch (failure) {
    case 'VERIFICATION_REQUIRED':
      return 'Verify your details first';
    case 'NO_DESTINATION':
      return 'No bank account on file';
    case 'UNVERIFIED_DESTINATION':
      return 'Your bank account is not confirmed';
    case 'INSUFFICIENT_BALANCE':
      return 'Not enough available';
    case 'ALREADY_REQUESTED':
      return 'A payout is already under way';
    case 'CONNECTION':
      return 'No connection';
    default:
      return 'Could not request that payout';
  }
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
