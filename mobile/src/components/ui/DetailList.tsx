/**
 * A label-and-value list.
 *
 * Used wherever a screen has to show a set of facts: a booking's spec, an
 * address, a settlement breakdown. Labels are muted and values are not, so the
 * eye lands on the answers rather than on the questions.
 */

import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { Text } from '@/components/ui/Text';
import { spacing } from '@/theme/tokens';

export function DetailRow({
  label,
  value,
  /** For money and other figures that should stand out. */
  emphasis = false,
}: {
  label: string;
  value: ReactNode;
  emphasis?: boolean;
}) {
  return (
    <View style={styles.row}>
      <Text variant="footnote" tone="muted" style={styles.label}>
        {label}
      </Text>
      {typeof value === 'string' || typeof value === 'number' ? (
        <Text
          variant={emphasis ? 'price' : 'footnote'}
          weight={emphasis ? 'semibold' : 'medium'}
          style={styles.value}
        >
          {value}
        </Text>
      ) : (
        <View style={styles.valueNode}>{value}</View>
      )}
    </View>
  );
}

export function DetailList({ children }: { children: ReactNode }) {
  return <View style={styles.list}>{children}</View>;
}

/**
 * Turns a spec key into something readable.
 *
 * The booking `details` payload is vertical-specific and served from the
 * server's spec, so the app cannot carry a label for every field without
 * hard-coding knowledge of each vertical. Formatting the key is the honest
 * general answer.
 */
export function humaniseKey(key: string): string {
  const spaced = key.replace(/[_-]+/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Renders an arbitrary spec value without assuming its shape. */
export function humaniseValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Not set';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.length ? value.map(humaniseValue).join(', ') : 'None';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

const styles = StyleSheet.create({
  list: { gap: spacing.md },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.lg },
  label: { flex: 1 },
  value: { flexShrink: 1, textAlign: 'right' },
  valueNode: { flexShrink: 1, alignItems: 'flex-end' },
});
