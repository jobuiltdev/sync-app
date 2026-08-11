import { zodResolver } from '@hookform/resolvers/zod';
import { Link } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { z } from 'zod';

import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { toFormErrors } from '@/features/auth/form-errors';
import { useLogin } from '@/features/auth/hooks';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

const schema = z.object({
  email: z.email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.'),
});

type FormValues = z.infer<typeof schema>;

export default function LoginScreen() {
  const { mutate, isPending, error } = useLogin();
  const { control, handleSubmit } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
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
            <Text style={styles.title}>Welcome back</Text>
            <Text style={styles.subtitle}>Sign in to continue.</Text>
          </View>

          {apiErrors.message ? (
            <View accessibilityRole="alert" style={styles.banner}>
              <Text style={styles.bannerText}>{apiErrors.message}</Text>
            </View>
          ) : null}

          <View style={styles.form}>
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
              name="password"
              render={({ field, fieldState }) => (
                <Field
                  label="Password"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={fieldState.error?.message ?? apiErrors.fields.password}
                  secureTextEntry
                  autoComplete="current-password"
                  textContentType="password"
                  placeholder="Your password"
                />
              )}
            />

            <Button
              label="Sign in"
              loading={isPending}
              onPress={handleSubmit((values) => mutate(values))}
            />
          </View>

          <Text style={styles.footer}>
            New to Sync?{' '}
            <Link href="/register" style={styles.link}>
              Create an account
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
  header: { gap: spacing.xs, paddingTop: spacing.xl },
  title: {
    fontSize: fontSizes.title1,
    fontWeight: fontWeights.bold,
    color: colors.ink,
    letterSpacing: -0.5,
  },
  subtitle: { fontSize: fontSizes.body, color: colors.inkMuted },
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
