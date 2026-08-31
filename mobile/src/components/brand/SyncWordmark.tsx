import Svg, { Path } from 'react-native-svg';
import type { SvgProps } from 'react-native-svg';

import {
  WORDMARK_ASPECT,
  WORDMARK_COLOR,
  WORDMARK_LETTERS,
  WORDMARK_STROKE_WIDTH,
  WORDMARK_VIEWBOX,
} from '@/components/brand/wordmark-geometry';
import { useTheme } from '@/theme/theme';

/**
 * The Sync wordmark.
 *
 * Four monoline letters from `wordmark-geometry`, which is also what the
 * exported assets are cut from, so the component and the files cannot disagree.
 *
 * ### Sizing
 *
 * Give it a `height` or a `width`, not both. Whichever is supplied, the other is
 * derived from the aspect ratio, so the letterforms can never be stretched by a
 * caller passing a box that does not match. Passing neither gives a 20 point
 * wordmark, which is the middle of the range it was drawn for.
 *
 * ### Colour
 *
 * Theme aware by default: near black on light, warm off white on dark. Those are
 * the wordmark's own values rather than the body ink, for the reason set out in
 * the geometry file. `color` overrides both, and `WORDMARK_COLOR` carries the
 * monochrome pair for anywhere a single ink is required.
 *
 * It is one colour by construction. There is no gradient, no second fill and no
 * shape that only works against a particular background.
 */

export interface SyncWordmarkProps extends Omit<SvgProps, 'color' | 'height' | 'width'> {
  /** Height in points. Width follows from the aspect ratio. */
  height?: number;
  /** Width in points, if it is easier to reason about. Ignored when `height` is
   *  given, so the two can never fight. */
  width?: number;
  /** Overrides the theme-aware default. */
  color?: string;
  /** Defaults to "Sync". Pass `accessibilityRole="none"` to hide it where the
   *  mark beside it already carries the name. */
  accessibilityLabel?: string;
}

/** What it draws at when nobody says. Mid range of the 18 to 28 it is cut for. */
const DEFAULT_HEIGHT = 20;

export function SyncWordmark({
  height,
  width,
  color,
  accessibilityLabel = 'Sync',
  ...props
}: SyncWordmarkProps) {
  // `scheme`, not `mode`. `mode` is the stored preference and can be "system",
  // which is not a colour; `scheme` is what that resolves to on this device.
  const { scheme } = useTheme();

  // Height wins. Deriving the other dimension rather than accepting both is what
  // makes distortion impossible rather than merely discouraged.
  const drawnHeight = height ?? (width !== undefined ? width / WORDMARK_ASPECT : DEFAULT_HEIGHT);
  const drawnWidth = drawnHeight * WORDMARK_ASPECT;

  const stroke = color ?? (scheme === 'dark' ? WORDMARK_COLOR.dark : WORDMARK_COLOR.light);

  return (
    <Svg
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="image"
      fill="none"
      height={drawnHeight}
      viewBox={`0 0 ${WORDMARK_VIEWBOX.width} ${WORDMARK_VIEWBOX.height}`}
      width={drawnWidth}
      {...props}
    >
      {WORDMARK_LETTERS.map((letter) => (
        <Path
          key={letter.id}
          id={letter.id}
          testID={letter.id}
          d={letter.d}
          stroke={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={WORDMARK_STROKE_WIDTH}
        />
      ))}
    </Svg>
  );
}
