import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { useCurrentUser } from '@/features/auth/hooks';
import { needsNewCode, toVerificationState } from '@/features/auth/phone-verification';
import {
  useConfirmEmailVerification,
  useConfirmPhoneVerification,
  useRequestEmailVerification,
  useRequestPhoneVerification,
  useUpdatePhone,
} from '@/features/auth/verification-hooks';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Phone verification.
 *
 * Where a customer lands when booking asks for a verified number, and reachable
 * from the account screen. The screen knows nothing about who sends the message:
 * it renders the domain states the API reports.
 */
export default function VerifyPhoneScreen() {
  const router = useRouter();
  const { data: user } = useCurrentUser();

  const updatePhone = useUpdatePhone();
  const requestCode = useRequestPhoneVerification();
  const confirmCode = useConfirmPhoneVerification();

  const requestEmail = useRequestEmailVerification();
  const confirmEmail = useConfirmEmailVerification();

  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [emailCode, setEmailCode] = useState('');
  const [now, setNow] = useState(() => Date.now());
  const [resendAt, setResendAt] = useState(0);

  const challenge = requestCode.data ?? null;
  const state =
    toVerificationState(confirmCode.error) ??
    toVerificationState(requestCode.error) ??
    toVerificationState(updatePhone.error);

  const emailState =
    toVerificationState(confirmEmail.error) ?? toVerificationState(requestEmail.error);

  const verified = user?.is_phone_verified ?? false;
  const emailVerified = user?.is_email_verified ?? false;
  const emailChallenge = requestEmail.data ?? null;

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const cooldown = Math.max(Math.ceil((resendAt - now) / 1000), 0);

  // The server owns the timing rules; the deadline is captured from whatever it
  // reports, on the way out of the request rather than during render.
  function sendCode() {
    setCode('');
    confirmCode.reset();
    requestCode.mutate(undefined, {
      onSuccess: (issued) =>
        setResendAt(Date.now() + issued.resend_available_in_seconds * 1000),
      onError: (error) => {
        const seconds = toVerificationState(error)?.retryAfterSeconds ?? 0;
        if (seconds > 0) setResendAt(Date.now() + seconds * 1000);
      },
    });
  }

  if (verified && emailVerified) {
    return (
      <SafeAreaView style={styles.screen}>
        <View style={styles.content}>
          <Text style={styles.title}>You are verified</Text>
          <Text style={styles.body}>
            {user?.phone} and {user?.email} are confirmed.
          </Text>
          <Button label="Continue" onPress={() => router.replace('/home')} />
        </View>
      </SafeAreaView>
    );
  }

  const hasPhone = Boolean(user?.phone);
  const awaitingCode = challenge !== null && !needsNewCode(state);

  return (
    <SafeAreaView style={styles.screen}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <Text style={styles.title}>Verify your phone</Text>
            <Text style={styles.body}>
              A provider on their way to you needs a number that reaches you. We ask for this
              once, before your first booking.
            </Text>
          </View>

          {state ? (
            <View accessibilityRole="alert" style={[styles.card, styles.cardError]}>
              <Text style={styles.body}>{state.message}</Text>
              {state.attemptsRemaining !== null ? (
                <Text style={styles.muted}>
                  {state.attemptsRemaining} attempt{state.attemptsRemaining === 1 ? '' : 's'} left
                </Text>
              ) : null}
            </View>
          ) : null}

          {!hasPhone ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Add your number</Text>
              <Field
                label="Phone number"
                value={phone}
                onChangeText={setPhone}
                keyboardType="phone-pad"
                autoComplete="tel"
                placeholder="0803 123 4567"
              />
              <Button
                label="Save number"
                loading={updatePhone.isPending}
                onPress={() => updatePhone.mutate(phone)}
              />
            </View>
          ) : (
            <View style={styles.card}>
              <View style={styles.row}>
                <Text style={styles.muted}>Number</Text>
                <Text style={styles.value}>{user?.phone}</Text>
              </View>
              <Button
                label="Use a different number"
                variant="secondary"
                onPress={() => updatePhone.reset()}
              />
            </View>
          )}

          {hasPhone && !awaitingCode ? (
            <Button
              label={cooldown > 0 ? `Send a code in ${cooldown}s` : 'Send me a code'}
              loading={requestCode.isPending}
              disabled={cooldown > 0}
              onPress={sendCode}
            />
          ) : null}

          {awaitingCode ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Enter the code</Text>
              <Text style={styles.muted}>Sent to {challenge.destination}</Text>
              <Field
                label="6 digit code"
                value={code}
                onChangeText={setCode}
                keyboardType="number-pad"
                autoComplete="sms-otp"
                textContentType="oneTimeCode"
                maxLength={6}
                placeholder="123456"
              />
              <Button
                label="Verify"
                loading={confirmCode.isPending}
                disabled={code.length < 4}
                onPress={() =>
                  confirmCode.mutate({ challengeId: challenge.challenge_id, code })
                }
              />
              <Button
                label={cooldown > 0 ? `Resend in ${cooldown}s` : 'Send a new code'}
                variant="secondary"
                disabled={cooldown > 0}
                loading={requestCode.isPending}
                onPress={sendCode}
              />
            </View>
          ) : null}

          <View style={styles.card}>
            <Text style={styles.cardTitle}>Email</Text>
            <View style={styles.row}>
              <Text style={styles.muted}>{user?.email}</Text>
              <Text style={styles.value}>{emailVerified ? 'Verified' : 'Not verified'}</Text>
            </View>

            {emailVerified ? null : emailChallenge ? (
              <>
                <Field
                  label="Emailed code"
                  value={emailCode}
                  onChangeText={setEmailCode}
                  keyboardType="number-pad"
                  maxLength={6}
                  placeholder="123456"
                />
                {emailState ? (
                  <Text accessibilityRole="alert" style={styles.error}>
                    {emailState.message}
                  </Text>
                ) : null}
                <Button
                  label="Verify email"
                  loading={confirmEmail.isPending}
                  disabled={emailCode.length < 4}
                  onPress={() =>
                    confirmEmail.mutate({
                      challengeId: emailChallenge.challenge_id,
                      code: emailCode,
                    })
                  }
                />
              </>
            ) : (
              <>
                {emailState ? (
                  <Text accessibilityRole="alert" style={styles.error}>
                    {emailState.message}
                  </Text>
                ) : null}
                <Button
                  label="Email me a code"
                  variant="secondary"
                  loading={requestEmail.isPending}
                  onPress={() => {
                    setEmailCode('');
                    confirmEmail.reset();
                    requestEmail.mutate();
                  }}
                />
              </>
            )}
          </View>

          <Button label="Back" variant="secondary" onPress={() => router.back()} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  flex: { flex: 1 },
  content: { padding: spacing.xl, gap: spacing.lg },
  header: { gap: spacing.sm, paddingTop: spacing.lg },
  title: {
    fontSize: fontSizes.title2,
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
  body: { fontSize: fontSizes.body, color: colors.inkSoft, lineHeight: 24 },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  value: { fontSize: fontSizes.footnote, fontWeight: fontWeights.medium, color: colors.ink },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md },
  error: { fontSize: fontSizes.caption, color: colors.danger },
});
