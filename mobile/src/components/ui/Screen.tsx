/**
 * The page shell.
 *
 * Every screen in the app is wrapped in one of these, which is what makes safe
 * areas and the floating navigation bar somebody else's problem exactly once
 * instead of eleven times.
 *
 * **Content must never disappear behind the tab bar.** The bar floats over the
 * scroll view rather than displacing it, so the scroll content carries bottom
 * padding equal to the bar, its dock gutter, and the home indicator. Getting
 * this wrong is invisible on a tall phone and hides the last row on a short
 * one, so it is computed rather than eyeballed.
 */

import type { ReactNode } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  RefreshControl,
  ScrollView,
  type ScrollViewProps,
  StyleSheet,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { usePalette } from '@/theme/theme';
import { TAB_BAR_HEIGHT, spacing } from '@/theme/tokens';

/** Bottom padding a scrolling screen needs to clear the floating bar. */
export function useTabBarClearance(): number {
  const insets = useSafeAreaInsets();
  return TAB_BAR_HEIGHT + Math.max(insets.bottom, spacing.md) + spacing.lg;
}

interface ScreenProps {
  children: ReactNode;
  /** Adds bottom clearance for the floating tab bar. Off for stack screens
   *  pushed above the tabs, which have no bar to clear. */
  tabBar?: boolean;
  /** Screens with their own scroll container (a FlatList) opt out. */
  scroll?: boolean;
  refreshing?: boolean;
  onRefresh?: () => void;
  /** Removes the horizontal padding, for edge-to-edge content. */
  bleed?: boolean;
  contentContainerStyle?: ScrollViewProps['contentContainerStyle'];
  /** Pinned to the bottom, above the safe area. For a form's primary action. */
  footer?: ReactNode;
}

export function Screen({
  children,
  tabBar = false,
  scroll = true,
  refreshing,
  onRefresh,
  bleed = false,
  contentContainerStyle,
  footer,
}: ScreenProps) {
  const palette = usePalette();
  const insets = useSafeAreaInsets();
  const clearance = useTabBarClearance();

  const padding = {
    paddingHorizontal: bleed ? 0 : spacing.xl,
    paddingBottom: tabBar ? clearance : spacing.xl,
  };

  const body = scroll ? (
    <ScrollView
      style={styles.flex}
      contentContainerStyle={[styles.content, padding, contentContainerStyle]}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
      refreshControl={
        onRefresh ? (
          <RefreshControl
            refreshing={Boolean(refreshing)}
            onRefresh={onRefresh}
            tintColor={palette.inkMuted}
            colors={[palette.primary]}
          />
        ) : undefined
      }
    >
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.flex, padding]}>{children}</View>
  );

  return (
    <View style={[styles.flex, { backgroundColor: palette.ground }]}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        // The header is already inside the safe area, so only the notch is
        // subtracted. Adding the full inset double-counts it and leaves a gap.
        keyboardVerticalOffset={insets.top}
      >
        {body}
        {footer ? (
          <View
            style={[
              styles.footer,
              {
                backgroundColor: palette.ground,
                borderTopColor: palette.hairline,
                paddingBottom: Math.max(insets.bottom, spacing.lg),
              },
            ]}
          >
            {footer}
          </View>
        ) : null}
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { paddingTop: spacing.md, gap: spacing.xl, flexGrow: 1 },
  footer: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth * 2,
    gap: spacing.sm,
  },
});
