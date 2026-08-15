/**
 * An initials avatar.
 *
 * No photo upload exists in this system, so an avatar here is always initials.
 * The tint is derived from the name rather than random, which means a person's
 * avatar is the same colour every time they appear and becomes a weak
 * recognition cue in a list of providers.
 */

import { StyleSheet, View } from 'react-native';

import { Text } from '@/components/ui/Text';
import { usePalette } from '@/theme/theme';

export function initialsOf(name: string): string {
  const parts = name
    .trim()
    .split(/\s+/)
    .filter((part) => /[a-z0-9]/i.test(part));

  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();

  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** A stable index from a name, so the same person keeps the same tint. */
function tintIndex(name: string, buckets: number): number {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) % 100000;
  }
  return hash % buckets;
}

export function Avatar({ name, size = 44 }: { name: string; size?: number }) {
  const palette = usePalette();

  // Drawn from the semantic soft tints rather than from invented colours, so an
  // avatar can never introduce a hue that is not already in the system.
  const tints = [
    { bg: palette.primarySoft, fg: palette.onPrimarySoft },
    { bg: palette.successSoft, fg: palette.success },
    { bg: palette.warningSoft, fg: palette.warning },
    { bg: palette.surfaceSunk, fg: palette.inkSoft },
  ];
  const tint = tints[tintIndex(name || '?', tints.length)];

  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[
        styles.avatar,
        { width: size, height: size, borderRadius: size / 3, backgroundColor: tint.bg },
      ]}
    >
      <Text
        variant="footnote"
        weight="bold"
        style={{ color: tint.fg, fontSize: size * 0.36, lineHeight: size * 0.44 }}
      >
        {initialsOf(name)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  avatar: { alignItems: 'center', justifyContent: 'center' },
});
