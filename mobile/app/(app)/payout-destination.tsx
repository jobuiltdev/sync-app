import { useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Header } from '@/components/ui/Header';
import { Icon } from '@/components/ui/Icon';
import { IconPlate, Pill } from '@/components/ui/Pill';
import { ListRow } from '@/components/ui/ListRow';
import { Screen } from '@/components/ui/Screen';
import { Sheet } from '@/components/ui/Sheet';
import { Skeleton, SkeletonList } from '@/components/ui/Skeleton';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { InlineError, SuccessNote } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import {
  useBanks,
  usePayoutDestination,
  useSavePayoutDestination,
  useVerifyPayoutDestination,
} from '@/features/payments/hooks';
import { usePalette } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

/**
 * Where a provider is paid.
 *
 * **The account number is never stored by this app or by the server.** The
 * server keeps a hash and the last four digits, which is why confirming an
 * account means typing the number again rather than tapping a button: nothing
 * has a copy to resolve.
 *
 * Verification is a real call to the bank, and the name it returns is shown
 * beside the name the provider typed. Those differing is the single most common
 * way money goes to the wrong person, so the comparison is made explicit rather
 * than left for somebody to notice.
 */
export default function PayoutDestinationScreen() {
  const router = useRouter();
  const palette = usePalette();

  const existing = usePayoutDestination();
  const save = useSavePayoutDestination();
  const verify = useVerifyPayoutDestination();
  const banks = useBanks();

  const [bank, setBank] = useState<{ code: string; name: string } | null>(null);
  const [accountName, setAccountName] = useState('');
  const [accountNumber, setAccountNumber] = useState('');
  const [confirmNumber, setConfirmNumber] = useState('');
  const [pickingBank, setPickingBank] = useState(false);
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState(false);

  const current = existing.data;
  const digits = accountNumber.replace(/\D/g, '');
  const confirmDigits = confirmNumber.replace(/\D/g, '');
  const isComplete = Boolean(bank) && accountName.trim().length > 0 && digits.length >= 10;

  const filtered = useMemo(() => {
    const all = banks.data ?? [];
    const needle = query.trim().toLowerCase();
    return needle ? all.filter((b) => b.name.toLowerCase().includes(needle)) : all;
  }, [banks.data, query]);

  const submit = () => {
    if (!isComplete || !bank) return;

    save.mutate(
      {
        bank_code: bank.code,
        bank_name: bank.name,
        account_name: accountName.trim(),
        account_number: digits,
      },
      {
        onSuccess: () => {
          setEditing(false);
          setAccountNumber('');
        },
      },
    );
  };

  const showForm = editing || (!existing.isPending && !current);

  return (
    <Screen>
      <Header onBack={() => router.back()} title="Payout account" />

      <Text variant="body" tone="muted">
        Payouts go to this account. We keep only the last four digits.
      </Text>

      {existing.isPending ? (
        <Skeleton width="100%" height={150} radius={18} />
      ) : current ? (
        <View style={styles.section}>
          <SectionHeader title="On file" />
          <Card>
            <View style={styles.accountHead}>
              <IconPlate icon="bank" tone={current.is_verified ? 'success' : 'warning'} size={44} />
              <View style={styles.accountText}>
                <Text variant="body" weight="semibold">
                  {current.bank_name}
                </Text>
                <Text variant="footnote" tone="soft">
                  {current.account_name}
                </Text>
                <Text variant="caption" tone="muted" style={styles.tabular}>
                  Ending {current.account_number_last4}
                </Text>
              </View>
              <Pill
                label={current.is_verified ? 'Confirmed' : 'Not confirmed'}
                tone={current.is_verified ? 'success' : 'warning'}
                dot={!current.is_verified}
              />
            </View>

            {current.is_verified ? (
              <View style={styles.confirmed}>
                <SuccessNote>
                  {`Your bank confirms this account belongs to ${current.resolved_account_name}.`}
                </SuccessNote>
                <Text variant="caption" tone="muted">
                  If that is not you, save the correct account below.
                </Text>
              </View>
            ) : (
              <View style={styles.confirmBlock}>
                <Text variant="footnote" tone="soft">
                  Type the account number again and we will check it with the bank. You
                  cannot be paid until this is done.
                </Text>
                <Field
                  label="Account number"
                  value={confirmNumber}
                  onChangeText={setConfirmNumber}
                  placeholder={`Ending ${current.account_number_last4}`}
                  keyboardType="number-pad"
                  maxLength={10}
                />
                <InlineError error={verify.error} />
                <Button
                  label="Confirm with the bank"
                  icon="shield"
                  loading={verify.isPending}
                  disabled={confirmDigits.length < 10}
                  onPress={() => verify.mutate(confirmDigits)}
                />
              </View>
            )}
          </Card>

          {!showForm ? (
            <Button
              label="Use a different account"
              variant="secondary"
              onPress={() => setEditing(true)}
            />
          ) : null}
        </View>
      ) : (
        <Card tone="warning">
          <View style={styles.none}>
            <IconPlate icon="bank" tone="warning" size={40} />
            <View style={styles.accountText}>
              <Text variant="body" weight="semibold">
                No account yet
              </Text>
              <Text variant="footnote" tone="soft">
                Add one before you request a payout.
              </Text>
            </View>
          </View>
        </Card>
      )}

      {showForm ? (
        <View style={styles.section}>
          <SectionHeader title={current ? 'Different account' : 'Add your account'} />

          <View style={styles.form}>
            <View style={styles.bankField}>
              <Text variant="footnote" weight="medium" tone="soft">
                Bank
              </Text>
              <Button
                label={bank?.name ?? 'Choose your bank'}
                variant="secondary"
                icon="chevronDown"
                onPress={() => setPickingBank(true)}
              />
            </View>

            <Field
              label="Account name"
              value={accountName}
              onChangeText={setAccountName}
              placeholder="As it appears at your bank"
              autoCapitalize="words"
            />
            <Field
              label="Account number"
              value={accountNumber}
              onChangeText={setAccountNumber}
              placeholder="0123456789"
              keyboardType="number-pad"
              maxLength={10}
              hint="Ten digits. We store only the last four."
            />

            <InlineError error={save.error} />

            <Button
              label="Save account"
              loading={save.isPending}
              disabled={!isComplete}
              onPress={submit}
            />
            {current ? (
              <Button label="Cancel" variant="ghost" onPress={() => setEditing(false)} />
            ) : null}
          </View>
        </View>
      ) : null}

      <Sheet
        visible={pickingBank}
        onClose={() => setPickingBank(false)}
        title="Choose your bank"
        subtitle="Search by name."
      >
        <Field label="Search" value={query} onChangeText={setQuery} placeholder="Guaranty" />

        {banks.isPending ? (
          <SkeletonList rows={5} showPlate={false} />
        ) : banks.error ? (
          <InlineError error={banks.error} />
        ) : filtered.length === 0 ? (
          <Text variant="footnote" tone="muted">
            No bank matches that name.
          </Text>
        ) : (
          filtered.map((option) => (
            <ListRow
              key={option.code}
              title={option.name}
              accessibilityLabel={option.name}
              onPress={() => {
                setBank({ code: option.code, name: option.name });
                setPickingBank(false);
                setQuery('');
              }}
              trailing={
                bank?.code === option.code ? (
                  <Icon name="check" size={19} color={palette.primary} strokeWidth={2.4} />
                ) : undefined
              }
            />
          ))
        )}
      </Sheet>
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.md },
  accountHead: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  accountText: { flex: 1, gap: spacing.xxs },
  tabular: { fontVariant: ['tabular-nums'] },
  confirmed: { marginTop: spacing.lg, gap: spacing.sm },
  confirmBlock: { marginTop: spacing.lg, gap: spacing.md },
  none: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  form: { gap: spacing.lg },
  bankField: { gap: spacing.sm },
});
