/**
 * A segmented control.
 *
 * Used where a screen has two or three views of the same subject and switching
 * between them should not feel like navigating. The selected segment is a
 * raised surface inside a sunk track, which reads as a physical switch without
 * needing an animation to explain itself.
 */

import { Pressable, StyleSheet, View } from 'react-native';

import { Badge } from '@/components/ui/Pill';
import { Text } from '@/components/ui/Text';
import { usePalette } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

export interface Segment<T extends string> {
  value: T;
  label: string;
  badge?: number;
}

export function Segmented<T extends string>({
  segments,
  value,
  onChange,
  accessibilityLabel,
}: {
  segments: Segment<T>[];
  value: T;
  onChange: (value: T) => void;
  accessibilityLabel?: string;
}) {
  const palette = usePalette();

  return (
    <View
      accessibilityRole="tablist"
      accessibilityLabel={accessibilityLabel}
      style={[styles.track, { backgroundColor: palette.surfaceSunk }]}
    >
      {segments.map((segment) => {
        const selected = segment.value === value;

        return (
          <Pressable
            key={segment.value}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            accessibilityLabel={
              segment.badge ? `${segment.label}, ${segment.badge} waiting` : segment.label
            }
            onPress={() => onChange(segment.value)}
            style={[
              styles.segment,
              selected && { backgroundColor: palette.surface },
            ]}
          >
            <Text
              variant="footnote"
              weight={selected ? 'semibold' : 'medium'}
              tone={selected ? 'default' : 'muted'}
              numberOfLines={1}
            >
              {segment.label}
            </Text>
            {segment.badge ? <Badge count={segment.badge} tone="primary" /> : null}
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    flexDirection: 'row',
    padding: 3,
    borderRadius: radii.control,
    gap: 3,
  },
  segment: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs + 2,
    minHeight: 38,
    borderRadius: radii.control - 3,
  },
});
