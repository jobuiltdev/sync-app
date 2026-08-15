/**
 * The header for a pushed screen.
 *
 * Written rather than configured, because the stack's own header cannot carry
 * the type scale or the back affordance this design wants, and half-styling it
 * would leave two header systems that drift apart.
 *
 * The title sits *below* the bar rather than inside it, as a large screen title
 * in the content flow. That is what gives every pushed screen the same
 * confident opening as a tab screen, and it leaves the bar itself nearly empty,
 * which is most of where "extremely clean" comes from.
 */

import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { usePalette } from '@/theme/theme';
import { MIN_TOUCH_TARGET, spacing } from '@/theme/tokens';

export function Header({
  onBack,
  title,
  action,
  /** A compact header keeps the title in the bar, for screens where vertical
   *  room matters more than presence. */
  compact = false,
}: {
  onBack?: () => void;
  title?: string;
  action?: ReactNode;
  compact?: boolean;
}) {
  const palette = usePalette();
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.bar, { paddingTop: insets.top + spacing.sm }]}>
      <View style={styles.row}>
        {onBack ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Go back"
            onPress={onBack}
            hitSlop={spacing.sm}
            style={({ pressed }) => [
              styles.back,
              {
                backgroundColor: pressed ? palette.surfaceSunk : palette.surface,
                borderColor: palette.hairline,
              },
            ]}
          >
            <Icon name="chevronLeft" size={20} color={palette.ink} />
          </Pressable>
        ) : (
          <View style={styles.back} />
        )}

        {compact && title ? (
          <Text variant="body" weight="semibold" numberOfLines={1} style={styles.compactTitle}>
            {title}
          </Text>
        ) : (
          <View style={styles.spacer} />
        )}

        <View style={styles.action}>{action}</View>
      </View>

      {!compact && title ? (
        <Text variant="title1" accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xs },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, minHeight: MIN_TOUCH_TARGET },
  back: {
    width: MIN_TOUCH_TARGET - 4,
    height: MIN_TOUCH_TARGET - 4,
    borderRadius: (MIN_TOUCH_TARGET - 4) / 2,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  spacer: { flex: 1 },
  compactTitle: { flex: 1, textAlign: 'center' },
  action: { minWidth: MIN_TOUCH_TARGET - 4, alignItems: 'flex-end' },
  title: { marginTop: spacing.md },
});
