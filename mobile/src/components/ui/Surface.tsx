/**
 * Containers and separators.
 *
 * The restraint here is deliberate. A card is a white rectangle on a warm
 * ground with a hairline and no shadow, because on a warm ground that is
 * already enough separation. Adding a shadow to every card is the single
 * fastest way to make an interface look like a 2019 admin dashboard.
 */

import type { ReactNode } from 'react';
import { StyleSheet, View, type ViewProps, type ViewStyle } from 'react-native';

import { Text } from '@/components/ui/Text';
import { usePalette } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

interface CardProps extends ViewProps {
  children: ReactNode;
  /** `plain` has no padding, for cards that contain their own rows. */
  padding?: 'regular' | 'tight' | 'none';
  /** Carries meaning, not decoration. Used for error and warning cards. */
  tone?: 'default' | 'danger' | 'warning' | 'success' | 'primary';
  /** Removes the border, for a card that sits on a sunk background. */
  borderless?: boolean;
}

export function Card({
  children,
  padding = 'regular',
  tone = 'default',
  borderless = false,
  style,
  ...rest
}: CardProps) {
  const palette = usePalette();

  const tones: Record<NonNullable<CardProps['tone']>, { bg: string; border: string }> = {
    default: { bg: palette.surface, border: palette.hairline },
    danger: { bg: palette.dangerSoft, border: palette.dangerSoft },
    warning: { bg: palette.warningSoft, border: palette.warningSoft },
    success: { bg: palette.successSoft, border: palette.successSoft },
    primary: { bg: palette.primarySoft, border: palette.primarySoft },
  };

  return (
    <View
      style={[
        styles.card,
        padding === 'regular' && styles.paddingRegular,
        padding === 'tight' && styles.paddingTight,
        {
          backgroundColor: tones[tone].bg,
          borderColor: borderless ? 'transparent' : tones[tone].border,
          borderWidth: borderless ? 0 : StyleSheet.hairlineWidth * 2,
        },
        style,
      ]}
      {...rest}
    >
      {children}
    </View>
  );
}

export function Divider({ inset = false, style }: { inset?: boolean; style?: ViewStyle }) {
  const palette = usePalette();
  return (
    <View
      style={[
        styles.divider,
        { backgroundColor: palette.hairlineSoft },
        inset && styles.dividerInset,
        style,
      ]}
    />
  );
}

/**
 * A section label.
 *
 * Tracked-out micro caps rather than a bold heading. It labels the group
 * without competing with the content inside it, which is what lets a screen
 * carry five sections and still feel calm.
 */
export function SectionHeader({
  title,
  action,
}: {
  title: string;
  action?: ReactNode;
}) {
  return (
    <View style={styles.sectionHeader}>
      <Text variant="overline" tone="muted">
        {title}
      </Text>
      {action}
    </View>
  );
}

/** A screen's opening block: a big title with optional supporting line. */
export function ScreenTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <View style={styles.screenTitle}>
      <Text variant="title1" accessibilityRole="header">
        {title}
      </Text>
      {subtitle ? (
        <Text variant="footnote" tone="muted">
          {subtitle}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.card, overflow: 'hidden' },
  paddingRegular: { padding: spacing.lg },
  paddingTight: { padding: spacing.md },
  divider: { height: StyleSheet.hairlineWidth * 2, width: '100%' },
  dividerInset: { marginLeft: spacing.lg },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 20,
  },
  screenTitle: { gap: spacing.xs },
});
