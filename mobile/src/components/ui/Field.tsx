import { StyleSheet, Text, TextInput, type TextInputProps, View } from 'react-native';

import { MIN_TOUCH_TARGET, colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

interface FieldProps extends TextInputProps {
  label: string;
  /** Message from the API or local validation. Shown below the input. */
  error?: string;
}

export function Field({ label, error, ...rest }: FieldProps) {
  return (
    <View style={styles.wrapper}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        // Error state is carried by the border and by the message text, never by
        // colour alone, so it survives a colour vision deficiency.
        style={[styles.input, !!error && styles.inputError]}
        placeholderTextColor={colors.inkMuted}
        {...rest}
      />
      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { gap: spacing.xs },
  label: {
    fontSize: fontSizes.footnote,
    fontWeight: fontWeights.medium,
    color: colors.inkSoft,
  },
  input: {
    minHeight: MIN_TOUCH_TARGET,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radii.control,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: fontSizes.body,
    color: colors.ink,
    backgroundColor: colors.surface,
  },
  inputError: { borderColor: colors.danger },
  error: { fontSize: fontSizes.caption, color: colors.danger },
});
