/**
 * The glass bottom navigation.
 *
 * This is the signature detail of the Sync interface, and the reason it works
 * is restraint. Three things make it feel like glass rather than like a
 * frosted rectangle stuck to the bottom of the screen:
 *
 * 1. **It is inset and floats.** The bar does not span the full width and does
 *    not touch the bottom edge. Content scrolls visibly past it on both sides,
 *    which is what sells the material as translucent; a full-bleed bar reads as
 *    an opaque footer no matter how much blur is behind it.
 * 2. **The blur is light and the tint is doing most of the work.** A heavy blur
 *    is expensive and looks like a filter. `intensity` stays low, with a
 *    theme-aware translucent fill over it carrying the warmth.
 * 3. **One hairline.** The top edge is separated by a barely-visible border
 *    rather than a shadow, which stops it reading as a floating card.
 *
 * ### Why expo-blur
 *
 * React Native has no blur primitive, and neither do any of the packages this
 * project already carries. `expo-blur` is the Expo SDK's own wrapper over the
 * platform blur (`UIVisualEffectView` on iOS, a render-node blur on Android 12+
 * with a graceful fallback below it), so it is a platform capability rather than
 * a third-party effect library. It is versioned with SDK 54 and adds no
 * JavaScript to the render path.
 *
 * ### Performance
 *
 * The blur view is mounted once for the lifetime of the tab navigator and never
 * re-renders on scroll, because nothing in it is derived from scroll position.
 * Android below 12 falls back to a solid tint automatically, which is the right
 * trade on the hardware where a live blur would actually cost frames.
 */

import { BlurView } from 'expo-blur';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Badge } from '@/components/ui/Pill';
import { Icon, type IconName } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { useTheme } from '@/theme/theme';
import { MIN_TOUCH_TARGET, TAB_BAR_HEIGHT, elevation, radii, spacing } from '@/theme/tokens';

export interface TabItem {
  key: string;
  label: string;
  icon: IconName;
  /** Count of things wanting attention. Zero renders nothing. */
  badge?: number;
}

interface TabBarProps {
  items: TabItem[];
  activeKey: string;
  onSelect: (key: string) => void;
}

export function TabBar({ items, activeKey, onSelect }: TabBarProps) {
  const { palette, scheme } = useTheme();
  const insets = useSafeAreaInsets();

  return (
    <View
      // Sits above content and ignores touches outside the bar itself, so the
      // inset gutters on either side do not swallow taps on the list beneath.
      pointerEvents="box-none"
      style={[styles.dock, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}
    >
      <View
        accessibilityRole="tablist"
        style={[styles.bar, { shadowColor: palette.shadow }, elevation.high]}
      >
        <BlurView
          intensity={scheme === 'dark' ? 40 : 28}
          tint={scheme === 'dark' ? 'dark' : 'light'}
          style={StyleSheet.absoluteFill}
        />
        {/* The tint over the blur. This is what carries the warmth: a bare
            platform blur is neutral grey and would drain the palette. */}
        <View
          style={[
            StyleSheet.absoluteFill,
            { backgroundColor: palette.glass, borderColor: palette.glassEdge },
            styles.tint,
          ]}
        />

        {items.map((item) => {
          const active = item.key === activeKey;

          return (
            <Pressable
              key={item.key}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              // Icons never carry meaning alone: the label is always visible and
              // the accessible name repeats it with any pending count.
              accessibilityLabel={
                item.badge ? `${item.label}, ${item.badge} waiting` : item.label
              }
              onPress={() => onSelect(item.key)}
              style={styles.tab}
            >
              <View>
                <Icon
                  name={item.icon}
                  size={23}
                  color={active ? palette.primary : palette.inkMuted}
                  // Weight, not just colour, marks the active tab.
                  strokeWidth={active ? 2.3 : 1.75}
                />
                {item.badge ? (
                  <View style={styles.badge}>
                    <Badge count={item.badge} tone="primary" />
                  </View>
                ) : null}
              </View>
              <Text
                variant="micro"
                style={{
                  color: active ? palette.primary : palette.inkMuted,
                  fontWeight: active ? '600' : '500',
                }}
              >
                {item.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  dock: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: spacing.xl,
  },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    height: TAB_BAR_HEIGHT,
    borderRadius: radii.pill,
    overflow: 'hidden',
  },
  tint: { borderRadius: radii.pill, borderWidth: StyleSheet.hairlineWidth * 2 },
  tab: {
    flex: 1,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
  },
  badge: { position: 'absolute', top: -6, right: -12 },
});
