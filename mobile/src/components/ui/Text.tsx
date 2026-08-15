/**
 * Typography.
 *
 * Every piece of text in the app goes through here with a named role. Screens
 * do not choose a font size, and that single rule is what keeps eleven screens
 * looking like one product.
 *
 * Hierarchy is carried by type rather than by containers. A section does not
 * need a card around it to read as a section if its heading is doing its job,
 * and removing those containers is most of what "extremely clean" means in
 * practice.
 */

import { Text as RNText, type TextProps as RNTextProps, StyleSheet, type TextStyle } from 'react-native';

import { usePalette } from '@/theme/theme';
import { fontSizes, fontWeights, lineHeights, tracking } from '@/theme/tokens';

export type TextVariant =
  /** Once per screen at most, for a number or a name that is the whole point. */
  | 'display'
  /** The screen's title. */
  | 'title1'
  /** A major block within a screen. */
  | 'title2'
  /** A card or group heading. */
  | 'title3'
  /** Default reading size. */
  | 'body'
  /** Body at a smaller size, for supporting detail. */
  | 'footnote'
  /** The smallest readable size. Timestamps, helper text. */
  | 'caption'
  /** Smaller still, and only where the label is paired with an icon that
   *  repeats its meaning. Tab labels and nothing else. */
  | 'micro'
  /** Tracked-out small caps for section labels. */
  | 'overline'
  /** Money. Tabular figures so columns line up. */
  | 'price'
  /** Money, large. */
  | 'priceLarge'
  /** Control labels. */
  | 'button';

export type TextTone = 'default' | 'soft' | 'muted' | 'primary' | 'success' | 'warning' | 'danger' | 'onPrimary';

export interface TextProps extends RNTextProps {
  variant?: TextVariant;
  tone?: TextTone;
  /** Overrides the variant's weight without leaving the scale. */
  weight?: keyof typeof fontWeights;
  center?: boolean;
}

export function Text({
  variant = 'body',
  tone = 'default',
  weight,
  center = false,
  style,
  ...rest
}: TextProps) {
  const palette = usePalette();

  const color = {
    default: palette.ink,
    soft: palette.inkSoft,
    muted: palette.inkMuted,
    primary: palette.primary,
    success: palette.success,
    warning: palette.warning,
    danger: palette.danger,
    onPrimary: palette.onPrimary,
  }[tone];

  return (
    <RNText
      style={[
        variants[variant],
        { color },
        weight ? { fontWeight: fontWeights[weight] } : null,
        center ? styles.center : null,
        style,
      ]}
      {...rest}
    />
  );
}

const styles = StyleSheet.create({ center: { textAlign: 'center' } });

const variants = StyleSheet.create({
  display: {
    fontSize: fontSizes.display,
    lineHeight: lineHeights.display,
    fontWeight: fontWeights.bold,
    letterSpacing: tracking.display,
  },
  title1: {
    fontSize: fontSizes.title1,
    lineHeight: lineHeights.title1,
    fontWeight: fontWeights.bold,
    letterSpacing: tracking.title1,
  },
  title2: {
    fontSize: fontSizes.title2,
    lineHeight: lineHeights.title2,
    fontWeight: fontWeights.bold,
    letterSpacing: tracking.title2,
  },
  title3: {
    fontSize: fontSizes.title3,
    lineHeight: lineHeights.title3,
    fontWeight: fontWeights.semibold,
    letterSpacing: tracking.title3,
  },
  body: {
    fontSize: fontSizes.body,
    lineHeight: lineHeights.body,
    fontWeight: fontWeights.regular,
  },
  footnote: {
    fontSize: fontSizes.footnote,
    lineHeight: lineHeights.footnote,
    fontWeight: fontWeights.regular,
  },
  caption: {
    fontSize: fontSizes.caption,
    lineHeight: lineHeights.caption,
    fontWeight: fontWeights.regular,
    letterSpacing: tracking.caption,
  },
  micro: {
    fontSize: fontSizes.micro,
    lineHeight: lineHeights.micro,
    fontWeight: fontWeights.medium,
  },
  overline: {
    fontSize: fontSizes.micro,
    lineHeight: lineHeights.micro,
    fontWeight: fontWeights.semibold,
    letterSpacing: tracking.overline,
    textTransform: 'uppercase',
  },
  price: {
    fontSize: fontSizes.body,
    lineHeight: lineHeights.body,
    fontWeight: fontWeights.semibold,
    // Money sits in columns all over this app. Proportional figures make those
    // columns shift width as the digits change, which reads as sloppy.
    fontVariant: ['tabular-nums'],
  },
  priceLarge: {
    fontSize: fontSizes.title1,
    lineHeight: lineHeights.title1,
    fontWeight: fontWeights.bold,
    letterSpacing: tracking.title1,
    fontVariant: ['tabular-nums'],
  },
  button: {
    fontSize: fontSizes.body,
    lineHeight: lineHeights.body,
    fontWeight: fontWeights.semibold,
  },
}) as Record<TextVariant, TextStyle>;
