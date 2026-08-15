/**
 * Pills, badges and status indicators.
 *
 * **Status is never carried by colour alone.** Every pill in this app pairs a
 * tone with a written label, and the ones that indicate live state also carry a
 * dot whose presence, not just its hue, distinguishes it. Someone who cannot
 * separate the green from the amber still reads "On the way".
 */

import type { ReactNode } from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';

import { Icon, type IconName } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { usePalette } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

export type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'live';

export function useToneColors(tone: Tone) {
  const palette = usePalette();

  return {
    neutral: { fg: palette.inkSoft, bg: palette.surfaceSunk },
    primary: { fg: palette.onPrimarySoft, bg: palette.primarySoft },
    success: { fg: palette.success, bg: palette.successSoft },
    warning: { fg: palette.warning, bg: palette.warningSoft },
    danger: { fg: palette.danger, bg: palette.dangerSoft },
    // Live work in progress reads as the brand colour: it is the thing the
    // person opened the app to look at.
    live: { fg: palette.onPrimarySoft, bg: palette.primarySoft },
  }[tone];
}

interface PillProps {
  label: string;
  tone?: Tone;
  /** Shows a leading dot. Reserved for states that are actively changing. */
  dot?: boolean;
  icon?: IconName;
  style?: ViewStyle;
}

export function Pill({ label, tone = 'neutral', dot = false, icon, style }: PillProps) {
  const { fg, bg } = useToneColors(tone);

  return (
    <View style={[styles.pill, { backgroundColor: bg }, style]}>
      {dot ? <View style={[styles.dot, { backgroundColor: fg }]} /> : null}
      {icon ? <Icon name={icon} size={13} color={fg} strokeWidth={2} /> : null}
      <Text variant="caption" weight="semibold" style={{ color: fg }} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

/** A count badge, for the number of things waiting. */
export function Badge({ count, tone = 'primary' }: { count: number; tone?: Tone }) {
  const { fg, bg } = useToneColors(tone);
  if (count <= 0) return null;

  return (
    <View style={[styles.badge, { backgroundColor: bg }]}>
      <Text variant="caption" weight="bold" style={{ color: fg }}>
        {count > 99 ? '99+' : count}
      </Text>
    </View>
  );
}

/** A chip used for selection, in filters and choice fields. */
export function Chip({
  label,
  selected = false,
  onPress,
  accessibilityLabel,
}: {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  accessibilityLabel?: string;
}) {
  const palette = usePalette();

  return (
    <View
      accessible
      accessibilityRole={onPress ? 'button' : 'text'}
      accessibilityState={{ selected }}
      accessibilityLabel={accessibilityLabel ?? label}
      onTouchEnd={onPress}
      style={[
        styles.chip,
        {
          backgroundColor: selected ? palette.primarySoft : palette.surface,
          borderColor: selected ? palette.primary : palette.hairline,
          borderWidth: selected ? 2 : StyleSheet.hairlineWidth * 2,
        },
      ]}
    >
      <Text
        variant="footnote"
        weight={selected ? 'semibold' : 'regular'}
        style={{ color: selected ? palette.onPrimarySoft : palette.inkSoft }}
      >
        {label}
      </Text>
    </View>
  );
}

/** A small circular icon plate. Used to give list rows an anchor. */
export function IconPlate({
  icon,
  tone = 'neutral',
  size = 42,
}: {
  icon: IconName;
  tone?: Tone;
  size?: number;
}) {
  const { fg, bg } = useToneColors(tone);

  return (
    <View
      style={[
        styles.plate,
        { backgroundColor: bg, width: size, height: size, borderRadius: size / 3 },
      ]}
    >
      <Icon name={icon} size={size * 0.48} color={fg} />
    </View>
  );
}

/** Wraps content that should be laid out as a row of pills. */
export function PillRow({ children }: { children: ReactNode }) {
  return <View style={styles.pillRow}>{children}</View>;
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs + 2,
    paddingHorizontal: spacing.md - 2,
    paddingVertical: spacing.xs + 2,
    borderRadius: radii.pill,
    alignSelf: 'flex-start',
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  badge: {
    minWidth: 20,
    height: 20,
    paddingHorizontal: 5,
    borderRadius: radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chip: {
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: spacing.sm + 2,
    borderRadius: radii.pill,
    minHeight: 40,
    justifyContent: 'center',
  },
  plate: { alignItems: 'center', justifyContent: 'center' },
  pillRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
});
