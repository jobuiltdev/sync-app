/**
 * The list row.
 *
 * Most of this app is lists, so this component carries most of its visual
 * character. It is a row rather than a card on purpose: a screen of stacked
 * cards, each with its own border and shadow, is the "giant cards everywhere"
 * look the design direction rules out. Rows grouped inside one card, separated
 * by inset hairlines, read as a single calm object.
 */

import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon, type IconName } from '@/components/ui/Icon';
import { IconPlate, type Tone } from '@/components/ui/Pill';
import { Text } from '@/components/ui/Text';
import { Divider } from '@/components/ui/Surface';
import { usePalette } from '@/theme/theme';
import { MIN_TOUCH_TARGET, spacing } from '@/theme/tokens';

interface ListRowProps {
  title: string;
  subtitle?: string;
  /** A third line, for detail that would crowd the subtitle. */
  meta?: string;
  icon?: IconName;
  iconTone?: Tone;
  /** Right-aligned content: a price, a pill, a switch. */
  trailing?: ReactNode;
  onPress?: () => void;
  /** Shows a chevron. Only for rows that navigate somewhere. */
  chevron?: boolean;
  destructive?: boolean;
  accessibilityLabel?: string;
  disabled?: boolean;
}

export function ListRow({
  title,
  subtitle,
  meta,
  icon,
  iconTone = 'neutral',
  trailing,
  onPress,
  chevron = false,
  destructive = false,
  accessibilityLabel,
  disabled = false,
}: ListRowProps) {
  const palette = usePalette();

  const content = (
    <>
      {icon ? <IconPlate icon={icon} tone={destructive ? 'danger' : iconTone} size={40} /> : null}

      <View style={styles.text}>
        <Text
          variant="body"
          weight="medium"
          tone={destructive ? 'danger' : 'default'}
          numberOfLines={2}
        >
          {title}
        </Text>
        {subtitle ? (
          <Text variant="footnote" tone="muted" numberOfLines={2}>
            {subtitle}
          </Text>
        ) : null}
        {meta ? (
          <Text variant="caption" tone="muted" numberOfLines={1}>
            {meta}
          </Text>
        ) : null}
      </View>

      {trailing ? <View style={styles.trailing}>{trailing}</View> : null}
      {chevron ? <Icon name="chevronRight" size={18} color={palette.inkMuted} /> : null}
    </>
  );

  if (!onPress) {
    return <View style={styles.row}>{content}</View>;
  }

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? title}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.row,
        pressed && { backgroundColor: palette.surfaceSunk },
        disabled && styles.disabled,
      ]}
    >
      {content}
    </Pressable>
  );
}

/**
 * Rows grouped into one card.
 *
 * Inserts the inset dividers so call sites do not have to, which is what stops
 * one screen having them and the next one not.
 */
export function RowGroup({ children }: { children: ReactNode }) {
  const items = Array.isArray(children) ? children.filter(Boolean) : [children];

  return (
    <>
      {items.map((child, index) => (
        <View key={index}>
          {index > 0 ? <Divider inset /> : null}
          {child}
        </View>
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    minHeight: MIN_TOUCH_TARGET + 12,
  },
  text: { flex: 1, gap: spacing.xxs },
  trailing: { alignItems: 'flex-end' },
  disabled: { opacity: 0.5 },
});
