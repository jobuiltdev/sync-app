/**
 * Loading placeholders.
 *
 * A skeleton rather than a spinner wherever the shape of the result is already
 * known. A spinner says "wait"; a skeleton says "here is what is coming", and
 * the screen does not jump when it arrives because the space was already the
 * right size.
 *
 * The pulse is opacity only, driven on the native thread, so a list of twelve
 * of these costs nothing on the mid-range Android hardware most customers here
 * are using.
 */

import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View, type ViewStyle } from 'react-native';

import { Card } from '@/components/ui/Surface';
import { usePalette } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

export function Skeleton({
  width = '100%',
  height = 16,
  radius = 8,
  style,
}: {
  width?: number | `${number}%`;
  height?: number;
  radius?: number;
  style?: ViewStyle;
}) {
  const palette = usePalette();
  const pulse = useRef(new Animated.Value(0.5)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 700,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0.5,
          duration: 700,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);

  return (
    <Animated.View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[
        { width, height, borderRadius: radius, backgroundColor: palette.surfaceSunk, opacity: pulse },
        style,
      ]}
    />
  );
}

/** The shape of a list row, repeated. Used wherever a list is loading. */
export function SkeletonList({ rows = 3, showPlate = true }: { rows?: number; showPlate?: boolean }) {
  return (
    <View style={styles.list}>
      {Array.from({ length: rows }).map((_, index) => (
        <Card key={index} padding="regular">
          <View style={styles.row}>
            {showPlate ? <Skeleton width={42} height={42} radius={radii.chip} /> : null}
            <View style={styles.rowText}>
              <Skeleton width="62%" height={16} />
              <Skeleton width="40%" height={13} />
            </View>
          </View>
        </Card>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  rowText: { flex: 1, gap: spacing.sm },
});
