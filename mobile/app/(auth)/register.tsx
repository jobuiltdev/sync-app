import { zodResolver } from '@hookform/resolvers/zod';
import { Link } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { toFormErrors } from '@/features/auth/form-errors';
import { useRegister } from '@/features/auth/hooks';
import { type RegisterFormValues, registerSchema } from '@/features/auth/register-schema';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';


export default function RegisterScreen() {
  const { mutate, isPending, error } = useRegister();
  const { control, handleSubmit } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { first_name: '', last_name: '', email: '', phone: '', password: '' },
  });

  const apiErrors = toFormErrors(error);

  return (
    <SafeAreaView style={styles.screen}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <Text style={styles.title}>Create your account</Text>
            <Text style={styles.subtitle}>
              You can start exploring straight away. Verifying your details comes later.
            </Text>
          </View>

          {apiErrors.message ? (
            <View accessibilityRole="alert" style={styles.banner}>
              <Text style={styles.bannerText}>{apiErrors.message}</Text>
            </View>
          ) : null}

          <View style={styles.form}>
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

          <Text style={styles.footer}>
            Already have an account?{' '}
            <Link href="/login" style={styles.link}>
              Sign in
            </Link>
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  flex: { flex: 1 },
  content: { padding: spacing.xl, gap: spacing.xl, flexGrow: 1 },
  header: { gap: spacing.xs, paddingTop: spacing.lg },
  title: {
    fontSize: fontSizes.title1,
    fontWeight: fontWeights.bold,
    color: colors.ink,
    letterSpacing: -0.5,
  },
  subtitle: { fontSize: fontSizes.body, color: colors.inkMuted, lineHeight: 24 },
  form: { gap: spacing.lg },
  banner: {
    backgroundColor: colors.dangerSoft,
    borderRadius: radii.control,
    borderWidth: 1,
    borderColor: colors.danger,
    padding: spacing.md,
  },
  bannerText: { color: colors.danger, fontSize: fontSizes.footnote },
  footer: { fontSize: fontSizes.footnote, color: colors.inkMuted, textAlign: 'center' },
  link: { color: colors.accent, fontWeight: fontWeights.semibold },
});
