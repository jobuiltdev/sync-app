/**
 * Design tokens.
 *
 * Everything visual reads from here. Components never hold a literal colour,
 * spacing value or font size, so the system can be adjusted in one place.
 * Phase 1 ships light only; the palette is shaped so a dark set can be added
 * alongside it without touching any component.
 */

export const colors = {
  // Neutrals carry the interface. Most screens are neutral with one accent element.
  ink: '#101C1A',
  inkSoft: '#3D4B48',
  inkMuted: '#66756F',
  hairline: '#DBE1DE',
  surface: '#FFFFFF',
  surfaceSunk: '#F1F4F2',
  ground: '#F7F9F7',

  // A single accent, reserved for primary actions and active state.
  accent: '#0B6E62',
  accentPressed: '#095A50',
  accentSoft: '#E0EFEB',
  onAccent: '#FFFFFF',

  // Semantic colours are separate from the accent and only ever carry meaning.
  success: '#1B7A4B',
  warning: '#9C6B1B',
  danger: '#A32B22',
  dangerSoft: '#FAEAE8',
} as const;

/** 4pt base scale. Nothing off the scale. */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

/** Radii are applied by role rather than picked per screen. */
export const radii = {
  control: 12,
  card: 16,
  sheet: 20,
  pill: 999,
} as const;

/** A seven step scale. Hierarchy comes from weight and size, not extra families. */
export const fontSizes = {
  caption: 12,
  footnote: 14,
  body: 16,
  callout: 18,
  title3: 22,
  title2: 28,
  title1: 34,
} as const;

export const fontWeights = {
  regular: '400',
  medium: '500',
  semibold: '600',
  bold: '700',
} as const;

export const lineHeights = {
  caption: 16,
  footnote: 20,
  body: 24,
  callout: 26,
  title3: 28,
  title2: 34,
  title1: 40,
} as const;

/**
 * Motion stays between 150 and 250ms with no overshoot bounce. Anything longer
 * reads as sluggish on the mid-range Android hardware most customers carry.
 */
export const motion = {
  fast: 150,
  base: 200,
  slow: 250,
} as const;

/** The minimum touch target we ship, in points. */
export const MIN_TOUCH_TARGET = 44;

export const theme = {
  colors,
  spacing,
  radii,
  fontSizes,
  fontWeights,
  lineHeights,
  motion,
} as const;

export type Theme = typeof theme;
