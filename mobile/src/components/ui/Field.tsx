/**
 * Text input.
 *
 * The focus treatment is the accent border rather than a glow, and the error
 * treatment is a border *and* a message, never colour alone. A red outline with
 * no words tells a colour-blind user only that something is wrong somewhere.
 */

import { useState } from 'react';
import { StyleSheet, TextInput, type TextInputProps, View } from 'react-native';

import { Text } from '@/components/ui/Text';
import { usePalette } from '@/theme/theme';
import { MIN_TOUCH_TARGET, fontSizes, radii, spacing } from '@/theme/tokens';

interface FieldProps extends TextInputProps {
  label: string;
  /** Message from the API or local validation. Shown below the input. */
  error?: string;
  /** Guidance shown when there is no error. */
  hint?: string;
  /** A unit or short label pinned inside the input, such as the naira sign. */
  prefix?: string;
}

export function Field({ label, error, hint, prefix, style, ...rest }: FieldProps) {
  const palette = usePalette();
  const [focused, setFocused] = useState(false);

  const borderColor = error
    ? palette.danger
    : focused
      ? palette.primary
      : palette.hairline;

  return (
    <View style={styles.wrapper}>
      <Text variant="footnote" weight="medium" tone="soft">
        {label}
      </Text>

      <View
        style={[
          styles.shell,
          {
            borderColor,
            backgroundColor: palette.surface,
            borderWidth: focused || error ? 2 : StyleSheet.hairlineWidth * 2,
          },
        ]}
      >
        {prefix ? (
          <Text variant="body" tone="muted">
            {prefix}
          </Text>
        ) : null}
        <TextInput
          accessibilityLabel={label}
          accessibilityHint={error ?? hint}
          style={[styles.input, { color: palette.ink }, style]}
          placeholderTextColor={palette.inkMuted}
          onFocus={(event) => {
            setFocused(true);
            rest.onFocus?.(event);
          }}
          onBlur={(event) => {
            setFocused(false);
            rest.onBlur?.(event);
          }}
          {...rest}
        />
      </View>

      {error ? (
        <Text variant="caption" tone="danger" accessibilityRole="alert">
          {error}
        </Text>
      ) : hint ? (
        <Text variant="caption" tone="muted">
          {hint}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { gap: spacing.sm },
  shell: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    minHeight: MIN_TOUCH_TARGET + 6,
    borderRadius: radii.control,
    paddingHorizontal: spacing.md,
  },
  input: { flex: 1, fontSize: fontSizes.body, paddingVertical: spacing.md },
});
