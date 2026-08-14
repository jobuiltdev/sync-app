import { useRouter } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { usePayoutDestination, useSavePayoutDestination } from '@/features/payments/hooks';
import { toPayoutOutcome } from '@/features/payments/outcomes';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Where a provider is paid.
 *
 * The account number is sent once and never comes back. What the screen can show
 * afterwards is the bank, the name on the account and the last four digits,
 * which is exactly what the server keeps. Changing the account means typing the
 * whole number again, and that is the intended trade: an account number nobody
 * stores is an account number nobody can leak.
 */
export default function PayoutDestinationScreen() {
  const router = useRouter();
  const existing = usePayoutDestination();
  const save = useSavePayoutDestination();

  const [bankName, setBankName] = useState('');
  const [bankCode, setBankCode] = useState('');
  const [accountName, setAccountName] = useState('');
  const [accountNumber, setAccountNumber] = useState('');

  const outcome = toPayoutOutcome(save.error);
  const current = existing.data;
  const digits = accountNumber.replace(/\D/g, '');
  const isComplete =
    bankName.trim().length > 0 &&
    bankCode.trim().length > 0 &&
    accountName.trim().length > 0 &&
    digits.length >= 10;

  const submit = () => {
    if (!isComplete) return;

    save.mutate(
      {
        bank_code: bankCode.trim(),
        bank_name: bankName.trim(),
        account_name: accountName.trim(),
        account_number: digits,
      },
      { onSuccess: () => router.back() },
    );
  };

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title}>Where you are paid</Text>
          <Text style={styles.muted}>
            Payouts go to this account. We keep the last four digits only.
          </Text>
        </View>

        {existing.isPending ? (
          <View style={styles.card}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : current ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>On file</Text>
            <Text style={styles.body}>{current.bank_name}</Text>
            <Text style={styles.body}>{current.account_name}</Text>
            <Text style={styles.account}>Ending {current.account_number_last4}</Text>
          </View>
        ) : (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>No account yet</Text>
            <Text style={styles.body}>Add one before you request a payout.</Text>
          </View>
        )}

        <Field
          label="Bank name"
          value={bankName}
          onChangeText={setBankName}
          placeholder="Guaranty Trust Bank"
          autoCapitalize="words"
        />
        <Field
          label="Bank code"
          value={bankCode}
          onChangeText={setBankCode}
          placeholder="058"
          keyboardType="number-pad"
        />
        <Field
          label="Account name"
          value={accountName}
          onChangeText={setAccountName}
          placeholder="The name on the account"
          autoCapitalize="words"
        />
        <Field
          label="Account number"
          value={accountNumber}
          onChangeText={setAccountNumber}
          placeholder="0123456789"
          keyboardType="number-pad"
          error={
            accountNumber.length > 0 && digits.length < 10
              ? 'A Nigerian account number is ten digits.'
              : undefined
          }
        />

        {outcome ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not save that account</Text>
            <Text style={styles.body}>{outcome.message}</Text>
          </View>
        ) : null}

        <Button
          label={current ? 'Replace account' : 'Save account'}
          loading={save.isPending}
          disabled={!isComplete}
          onPress={submit}
        />
        <Button label="Back" variant="secondary" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
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
    gap: spacing.xs,
  },
  cardError: { borderColor: colors.danger, backgroundColor: colors.dangerSoft, gap: spacing.md },
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  account: { fontSize: fontSizes.footnote, color: colors.inkMuted, fontVariant: ['tabular-nums'] },
});
