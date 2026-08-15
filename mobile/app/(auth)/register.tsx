import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useRouter } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Header } from '@/components/ui/Header';
import { Screen } from '@/components/ui/Screen';
import { InlineError } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { toFormErrors } from '@/features/auth/form-errors';
import { useRegister } from '@/features/auth/hooks';
import { type RegisterFormValues, registerSchema } from '@/features/auth/register-schema';
import { usePalette } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

export default function RegisterScreen() {
  const router = useRouter();
  const palette = usePalette();
  const { mutate, isPending, error } = useRegister();
  const { control, handleSubmit } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { first_name: '', last_name: '', email: '', phone: '', password: '' },
  });

  const apiErrors = toFormErrors(error);

  return (
    <Screen>
      <Header onBack={() => router.back()} />

      <View style={styles.head}>
        <Text variant="title1" accessibilityRole="header">
          Create your account
        </Text>
        <Text variant="body" tone="muted">
          You can start exploring straight away. Verifying your details comes later.
        </Text>
      </View>

      {apiErrors.message ? <InlineError error={error} /> : null}

      <View style={styles.form}>
        <View style={styles.names}>
          <View style={styles.name}>
            <Controller
              control={control}
              name="first_name"
              render={({ field, fieldState }) => (
                <Field
                  label="First name"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? apiErrors.fields.first_name}
                  autoComplete="given-name"
                  placeholder="Ada"
                />
              )}
            />
          </View>
          <View style={styles.name}>
            <Controller
              control={control}
              name="last_name"
              render={({ field, fieldState }) => (
                <Field
                  label="Last name"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? apiErrors.fields.last_name}
                  autoComplete="family-name"
                  placeholder="Okeke"
                />
              )}
            />
          </View>
        </View>

        <Controller
          control={control}
          name="email"
          render={({ field, fieldState }) => (
            <Field
              label="Email"
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={fieldState.error?.message ?? apiErrors.fields.email}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              textContentType="emailAddress"
              placeholder="you@example.com"
            />
          )}
        />

        <Controller
          control={control}
          name="phone"
          render={({ field, fieldState }) => (
            <Field
              label="Phone"
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={fieldState.error?.message ?? apiErrors.fields.phone}
              hint="We use this to reach you about a booking."
              autoComplete="tel"
              keyboardType="phone-pad"
              placeholder="0803 123 4567"
            />
          )}
        />

        <Controller
          control={control}
          name="password"
          render={({ field, fieldState }) => (
            <Field
              label="Password"
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={fieldState.error?.message ?? apiErrors.fields.password}
              secureTextEntry
              autoComplete="new-password"
              textContentType="newPassword"
              placeholder="At least 10 characters"
            />
          )}
        />

        <Button
          label="Create account"
          loading={isPending}
          onPress={handleSubmit((values) => mutate({ ...values, phone: values.phone.trim() }))}
        />
      </View>

      <Text variant="footnote" tone="muted" center>
        Already have an account?{' '}
        <Link href="/login" style={{ color: palette.primary, fontWeight: '600' }}>
          Sign in
        </Link>
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  head: { gap: spacing.xs },
  form: { gap: spacing.lg },
  // Two short fields share a row rather than each taking a full line, which
  // keeps the form to one screen on a small phone.
  names: { flexDirection: 'row', gap: spacing.md },
  name: { flex: 1 },
});
