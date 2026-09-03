/**
 * A bottom sheet.
 *
 * Used for choices that belong to the screen you are on: picking a bank,
 * choosing a state, confirming a cancellation. Pushing a whole route for those
 * loses the person's place for no benefit.
 *
 * Presentation animates from below with a scrim behind it, both fast. The
 * gesture is a tap on the scrim or the close control; a drag-to-dismiss would
 * mean a gesture handler and a pan responder for something a close button
 * already does.
 */

import { type ReactNode, useEffect, useRef } from 'react';
import { Animated, Easing, Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { usePalette } from '@/theme/theme';
import { MIN_TOUCH_TARGET, motion, radii, spacing } from '@/theme/tokens';

export function Sheet({
  visible,
  onClose,
  title,
  subtitle,
  children,
}: {
  visible: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const palette = usePalette();
  const insets = useSafeAreaInsets();
  const slide = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(slide, {
      toValue: visible ? 1 : 0,
      duration: visible ? motion.base : motion.fast,
      easing: visible ? Easing.out(Easing.cubic) : Easing.in(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [visible, slide]);

  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={onClose}>
      <View style={styles.root}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Close"
          onPress={onClose}
          style={styles.scrimTouch}
        >
          <Animated.View
            style={[StyleSheet.absoluteFill, { backgroundColor: palette.scrim, opacity: slide }]}
          />
        </Pressable>

        <Animated.View
          style={[
            styles.sheet,
            {
              backgroundColor: palette.surface,
              paddingBottom: Math.max(insets.bottom, spacing.lg),
              transform: [
                { translateY: slide.interpolate({ inputRange: [0, 1], outputRange: [420, 0] }) },
              ],
            },
          ]}
        >
          <View style={[styles.grabber, { backgroundColor: palette.hairline }]} />

          <View style={styles.head}>
            <View style={styles.headText}>
              <Text variant="title3" accessibilityRole="header">
                {title}
              </Text>
              {subtitle ? (
                <Text variant="footnote" tone="muted">
                  {subtitle}
                </Text>
              ) : null}
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Close"
              onPress={onClose}
              hitSlop={spacing.sm}
              style={[styles.close, { backgroundColor: palette.surfaceSunk }]}
            >
              <Icon name="close" size={18} color={palette.inkSoft} />
            </Pressable>
          </View>

          <ScrollView
            style={styles.body}
            contentContainerStyle={styles.bodyContent}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            {children}
          </ScrollView>
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, justifyContent: 'flex-end' },
  scrimTouch: { ...StyleSheet.absoluteFill },
  sheet: {
    borderTopLeftRadius: radii.sheet,
    borderTopRightRadius: radii.sheet,
    maxHeight: '82%',
    paddingHorizontal: spacing.xl,
  },
  grabber: {
    width: 36,
    height: 4,
    borderRadius: 2,
    alignSelf: 'center',
    marginTop: spacing.md,
  },
  head: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
  },
  headText: { flex: 1, gap: spacing.xxs },
  close: {
    width: MIN_TOUCH_TARGET - 8,
    height: MIN_TOUCH_TARGET - 8,
    borderRadius: (MIN_TOUCH_TARGET - 8) / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { flexGrow: 0 },
  bodyContent: { paddingBottom: spacing.md, gap: spacing.sm },
});
