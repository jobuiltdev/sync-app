import { useRouter } from 'expo-router';
import { useRef, useState } from 'react';
import {
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Icon } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { type Slide, SLIDES } from '@/features/onboarding/slides';
import { useOnboarding } from '@/features/onboarding/hooks';
import { usePalette } from '@/theme/theme';
import { MIN_TOUCH_TARGET, radii, spacing } from '@/theme/tokens';

/**
 * The introduction.
 *
 * A horizontal pager rather than a stack of routes: swiping between four cards
 * is one gesture people already know, and the back button on a route-based
 * carousel is ambiguous about whether it means "previous slide" or "leave".
 *
 * **Skippable from the first frame.** Somebody who already knows what Sync is
 * should be one tap from the door. An introduction that cannot be dismissed is
 * an advert.
 *
 * The page indicator is a row of bars where the active one is wider, not just a
 * different colour, so position is legible without relying on hue.
 */
export default function OnboardingScreen() {
  const router = useRouter();
  const palette = usePalette();
  const { width } = useWindowDimensions();
  const { complete } = useOnboarding();

  const scrollRef = useRef<ScrollView | null>(null);
  const [index, setIndex] = useState(0);

  const isLast = index === SLIDES.length - 1;

  const leave = async () => {
    await complete();
    router.replace('/welcome');
  };

  const next = () => {
    if (isLast) {
      void leave();
      return;
    }
    scrollRef.current?.scrollTo({ x: width * (index + 1), animated: true });
  };

  const onScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    // Derived from the offset rather than tracked separately, so a swipe and a
    // tap on the arrow can never disagree about which slide is showing.
    const page = Math.round(event.nativeEvent.contentOffset.x / width);
    if (page !== index) setIndex(page);
  };

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: palette.ground }]}>
      <View style={styles.top}>
        <Text variant="overline" tone="primary">
          Sync
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Skip the introduction"
          hitSlop={spacing.md}
          onPress={() => void leave()}
        >
          <Text variant="footnote" tone="muted" weight="medium">
            Skip
          </Text>
        </Pressable>
      </View>

      <ScrollView
        ref={scrollRef}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={onScroll}
        scrollEventThrottle={32}
        style={styles.pager}
      >
        {SLIDES.map((slide) => (
          <SlideView key={slide.key} slide={slide} width={width} />
        ))}
      </ScrollView>

      <View style={styles.controls}>
        <View
          // One accessible node, not four. Without `accessible` a screen reader
          // walks past four unlabelled dots instead of hearing the position once.
          accessible
          accessibilityRole="progressbar"
          accessibilityLabel={`Step ${index + 1} of ${SLIDES.length}`}
          style={styles.dots}
        >
          {SLIDES.map((slide, i) => (
            <View
              key={slide.key}
              style={[
                styles.dot,
                {
                  // Width as well as colour: position stays readable without
                  // depending on the hue being perceived.
                  width: i === index ? 22 : 8,
                  backgroundColor: i === index ? palette.primary : palette.hairline,
                },
              ]}
            />
          ))}
        </View>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel={isLast ? 'Get started' : 'Next'}
          onPress={next}
          style={({ pressed }) => [
            styles.next,
            { backgroundColor: pressed ? palette.primaryPressed : palette.primary },
          ]}
        >
          <Icon
            name={isLast ? 'check' : 'arrowRight'}
            size={22}
            color={palette.onPrimary}
            strokeWidth={2.2}
          />
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

/**
 * One card.
 *
 * The art is three glyphs from the app's own icon set rather than an
 * illustration: it cannot drift from the product, it costs nothing to ship, and
 * it looks like the rest of Sync instead of like stock artwork.
 */
function SlideView({ slide, width }: { slide: Slide; width: number }) {
  const palette = usePalette();

  return (
    <View style={[styles.slide, { width }]}>
      <View style={styles.art}>
        <View style={[styles.artPlate, { backgroundColor: palette.primarySoft }]}>
          <Icon name={slide.icon} size={64} color={palette.primary} strokeWidth={1.5} />
        </View>
        <View
          style={[styles.satellite, styles.satelliteLeft, { backgroundColor: palette.surface, borderColor: palette.hairline }]}
        >
          <Icon name={slide.supporting[0]} size={22} color={palette.inkSoft} />
        </View>
        <View
          style={[styles.satellite, styles.satelliteRight, { backgroundColor: palette.surface, borderColor: palette.hairline }]}
        >
          <Icon name={slide.supporting[1]} size={22} color={palette.inkSoft} />
        </View>
      </View>

      <View style={styles.copy}>
        <Text variant="title1" accessibilityRole="header">
          {slide.title}
        </Text>
        <Text variant="body" tone="muted">
          {slide.body}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  top: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
  },
  pager: { flex: 1 },
  slide: { paddingHorizontal: spacing.xl, justifyContent: 'center', gap: spacing.xxl },
  art: { alignItems: 'center', justifyContent: 'center', height: 220 },
  artPlate: {
    width: 148,
    height: 148,
    borderRadius: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  satellite: {
    position: 'absolute',
    width: 54,
    height: 54,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  satelliteLeft: { left: '14%', top: 24 },
  satelliteRight: { right: '14%', bottom: 24 },
  copy: { gap: spacing.md },
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.lg,
    minHeight: MIN_TOUCH_TARGET + 16,
  },
  dots: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  dot: { height: 8, borderRadius: 4 },
  next: {
    width: MIN_TOUCH_TARGET + 12,
    height: MIN_TOUCH_TARGET + 12,
    borderRadius: radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
