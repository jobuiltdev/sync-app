import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Header } from '@/components/ui/Header';
import { IconPlate } from '@/components/ui/Pill';
import { Screen } from '@/components/ui/Screen';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { InlineError, SuccessNote } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { useCurrentUser } from '@/features/auth/hooks';
import { needsNewCode, toVerificationState } from '@/features/auth/phone-verification';
import {
  useConfirmEmailVerification,
  useConfirmPhoneVerification,
  useRequestEmailVerification,
  useRequestPhoneVerification,
  useUpdatePhone,
} from '@/features/auth/verification-hooks';
import { spacing } from '@/theme/tokens';

/**
 * Verification, as a guided flow rather than a wall.
 *
 * Both channels live on one screen because both are needed to work as a
 * provider, and sending somebody between two screens to do the same thing twice
 * is how a five-minute task starts feeling like paperwork.
 *
 * **Every timing rule is the server's.** The cooldown counts down from whatever
 * the server reported, never from a local guess, so the button and the endpoint
 * agree about when a resend is allowed. Codes are never displayed, never logged,
 * and never read back from anything the app holds.
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
      onSuccess: (issued) => setResendAt(Date.now() + issued.resend_available_in_seconds * 1000),
      onError: (error) => {
        const seconds = toVerificationState(error)?.retryAfterSeconds ?? 0;
        if (seconds > 0) setResendAt(Date.now() + seconds * 1000);
      },
    });
  }

  if (verified && emailVerified) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <View style={styles.done}>
          <IconPlate icon="shield" tone="success" size={64} />
          <View style={styles.doneText}>
            <Text variant="title1" center accessibilityRole="header">
              You are verified
            </Text>
            <Text variant="footnote" tone="muted" center>
              {user?.phone} and {user?.email} are confirmed. You can book and take work.
            </Text>
          </View>
          <Button label="Continue" fullWidth={false} onPress={() => router.replace('/home')} />
        </View>
      </Screen>
    );
  }

  const hasPhone = Boolean(user?.phone);
  const awaitingCode = challenge !== null && !needsNewCode(state);

  return (
    <Screen>
      <Header onBack={() => router.back()} title="Verify your details" />

      <Text variant="body" tone="muted">
        Booking needs a verified phone. Taking work needs a verified email too.
      </Text>

      {/* --- phone ---------------------------------------------------------- */}
      <View style={styles.section}>
        <SectionHeader title="Phone" />

        {verified ? (
          <SuccessNote>{`${user?.phone} is verified.`}</SuccessNote>
        ) : (
          <Card>
            <View style={styles.block}>
              {!hasPhone ? (
                <>
                  <Text variant="footnote" tone="soft">
                    Add the number we should send your code to.
                  </Text>
                  <Field
                    label="Phone number"
                    value={phone}
                    onChangeText={setPhone}
                    keyboardType="phone-pad"
                    autoComplete="tel"
                    placeholder="0803 123 4567"
                    error={state?.message}
                  />
                  <Button
                    label="Save number"
                    loading={updatePhone.isPending}
                    onPress={() => updatePhone.mutate(phone)}
                  />
                </>
              ) : awaitingCode ? (
                <>
                  <Text variant="footnote" tone="soft">
                    We sent a six digit code to {challenge?.destination ?? user?.phone}.
                  </Text>
                  <Field
                    label="Verification code"
                    value={code}
                    onChangeText={setCode}
                    keyboardType="number-pad"
                    // One-time-code autofill: the code arrives by SMS and
                    // retyping it is the slowest part of signing up.
                    textContentType="oneTimeCode"
                    autoComplete="sms-otp"
                    maxLength={6}
                    placeholder="123456"
                    error={state?.message}
                    hint={
                      state?.attemptsRemaining !== null && state?.attemptsRemaining !== undefined
                        ? `${state.attemptsRemaining} attempt${state.attemptsRemaining === 1 ? '' : 's'} left`
                        : undefined
                    }
                  />
                  <Button
                    label="Confirm"
                    loading={confirmCode.isPending}
                    disabled={code.length < 6}
                    onPress={() =>
                      confirmCode.mutate({ challengeId: challenge.challenge_id, code })
                    }
                  />
                  <Button
                    label={cooldown > 0 ? `Send again in ${cooldown}s` : 'Send a new code'}
                    variant="ghost"
                    disabled={cooldown > 0 || requestCode.isPending}
                    loading={requestCode.isPending}
                    onPress={sendCode}
                  />
                </>
              ) : (
                <>
                  <Text variant="footnote" tone="soft">
                    We will text a six digit code to {user?.phone}.
                  </Text>
                  {state ? <InlineError error={requestCode.error ?? confirmCode.error} /> : null}
                  <Button
                    label={cooldown > 0 ? `Send again in ${cooldown}s` : 'Send me a code'}
                    loading={requestCode.isPending}
                    disabled={cooldown > 0}
                    onPress={sendCode}
                  />
                </>
              )}
            </View>
          </Card>
        )}
      </View>

      {/* --- email ---------------------------------------------------------- */}
      <View style={styles.section}>
        <SectionHeader title="Email" />

        {emailVerified ? (
          <SuccessNote>{`${user?.email} is verified.`}</SuccessNote>
        ) : (
          <Card>
            <View style={styles.block}>
              {emailChallenge && !needsNewCode(emailState) ? (
                <>
                  <Text variant="footnote" tone="soft">
                    We sent a code to {emailChallenge.destination}.
                  </Text>
                  <Field
                    label="Verification code"
                    value={emailCode}
                    onChangeText={setEmailCode}
                    keyboardType="number-pad"
                    textContentType="oneTimeCode"
                    maxLength={6}
                    placeholder="123456"
                    error={emailState?.message}
                  />
                  <Button
                    label="Confirm email"
                    loading={confirmEmail.isPending}
                    disabled={emailCode.length < 6}
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
                  <Text variant="footnote" tone="soft">
                    Needed before you can accept a job or be paid out.
                  </Text>
                  {emailState ? <InlineError error={requestEmail.error} /> : null}
                  <Button
                    label="Email me a code"
                    variant="secondary"
                    loading={requestEmail.isPending}
                    onPress={() => requestEmail.mutate()}
                  />
                </>
              )}
            </View>
          </Card>
        )}
      </View>

      <Text variant="caption" tone="muted">
        Codes expire shortly and can only be used once. We never ask for your code
        anywhere except on this screen.
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.md },
  block: { gap: spacing.md },
  done: { alignItems: 'center', gap: spacing.xl, paddingVertical: spacing.xxl },
  doneText: { gap: spacing.xs, alignItems: 'center' },
});
