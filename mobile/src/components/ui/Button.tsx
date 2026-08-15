/**
 * Buttons.
 *
 * Four variants and no more. Every extra button style is another decision at
 * every call site and another way for two screens to disagree about what the
 * main action looks like.
 *
 * Press feedback is a scale of 0.98 and a colour change, both fast. A button
 * that visibly animates on press feels slow; one that does nothing feels
 * broken.
 */

import { useRef } from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  type PressableProps,
  StyleSheet,
  View,
} from 'react-native';

import { Icon, type IconName } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { usePalette } from '@/theme/theme';
import { MIN_TOUCH_TARGET, motion, radii, spacing } from '@/theme/tokens';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'regular' | 'compact';

interface ButtonProps extends Omit<PressableProps, 'children' | 'style'> {
  label: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: IconName;
  /** Stretches to fill its row. Buttons in a form are full width; buttons in a
   *  card header are not. */
  fullWidth?: boolean;
}

export function Button({
  label,
  variant = 'primary',
  size = 'regular',
  loading = false,
  icon,
  fullWidth = true,
  disabled,
  ...rest
}: ButtonProps) {
  const palette = usePalette();
  const isDisabled = Boolean(disabled) || loading;
  const scale = useRef(new Animated.Value(1)).current;

  const press = (to: number) => {
    Animated.timing(scale, {
      toValue: to,
      duration: motion.instant,
      useNativeDriver: true,
    }).start();
  };

  const surfaces: Record<ButtonVariant, { rest: string; pressed: string; border?: string }> = {
    primary: { rest: palette.primary, pressed: palette.primaryPressed },
    secondary: {
      rest: palette.surface,
      pressed: palette.surfaceSunk,
      border: palette.hairline,
    },
    ghost: { rest: 'transparent', pressed: palette.surfaceSunk },
    danger: { rest: palette.danger, pressed: palette.dangerPressed },
  };

  const tone = variant === 'primary' || variant === 'danger' ? 'onPrimary' : 'default';
  const spinner = variant === 'primary' || variant === 'danger' ? palette.onPrimary : palette.primary;
  const surface = surfaces[variant];

  return (
    <Animated.View style={[{ transform: [{ scale }] }, fullWidth && styles.grow]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ disabled: isDisabled, busy: loading }}
        disabled={isDisabled}
        onPressIn={() => press(0.98)}
        onPressOut={() => press(1)}
        style={({ pressed }) => [
          styles.base,
          size === 'compact' && styles.compact,
          {
            backgroundColor: pressed && !isDisabled ? surface.pressed : surface.rest,
            borderWidth: surface.border ? StyleSheet.hairlineWidth * 2 : 0,
            borderColor: surface.border,
          },
          isDisabled && styles.disabled,
        ]}
        {...rest}
      >
        {loading ? (
          <ActivityIndicator color={spinner} />
        ) : (
          <View style={styles.content}>
            {icon ? (
              <Icon
                name={icon}
                size={18}
                color={tone === 'onPrimary' ? palette.onPrimary : palette.ink}
              />
            ) : null}
            <Text variant="button" tone={tone} numberOfLines={1}>
              {label}
            </Text>
          </View>
        )}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  grow: { alignSelf: 'stretch' },
  base: {
    minHeight: MIN_TOUCH_TARGET + 8,
    borderRadius: radii.control,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  compact: {
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: spacing.md,
    borderRadius: radii.chip,
  },
  content: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  disabled: { opacity: 0.45 },
});
