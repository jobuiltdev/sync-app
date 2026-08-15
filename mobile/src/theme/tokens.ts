/**
 * Design tokens.
 *
 * Everything visual reads from here. Components never hold a literal colour,
 * spacing value or font size, so the system can be adjusted in one place.
 *
 * ### The Sync visual direction
 *
 * Warm, confident, modern, extremely clean. Each of those is a decision made
 * here rather than a mood described in a document:
 *
 * **Warm** is in the neutrals. Every grey in this file carries a red and yellow
 * bias, so the backgrounds read as paper and sand rather than as aluminium. A
 * neutral grey interface is the default outcome of picking colours from a
 * generic palette, and it is what made the first version of this app feel like
 * a tool rather than a product.
 *
 * **Confident** is the single accent. One colour carries every action in the
 * app, and it is a saturated burnt sienna rather than the blue or emerald that
 * a marketplace is expected to use. Nothing else competes with it, which is
 * what lets it stay quiet and still be obvious.
 *
 * **Modern** is the restraint: hairline borders, one shadow that barely
 * registers, and hierarchy carried by type rather than by boxes.
 *
 * **Extremely clean** is the scale discipline. Seven spacing steps, four radii,
 * eight type sizes. A value that is not on a scale is a value somebody picked
 * to make one screen look right, and it is how a design system dies.
 *
 * Every foreground and background pair below is checked against WCAG AA at 4.5:1
 * and the palette was adjusted until all of them passed, rather than being
 * chosen and hoped for.
 */

/** A resolved palette. Light and dark both satisfy this shape, so a component
 *  reading a colour never learns which mode it is in. */
export interface Palette {
  /** The page behind everything. */
  ground: string;
  /** Raised content: cards, sheets, inputs. */
  surface: string;
  /** Recessed content: pressed states, skeletons, inert chips. */
  surfaceSunk: string;
  /** A surface that sits on another surface, used inside cards. */
  surfaceRaised: string;
  /** One hairline, used sparingly. Borders are the first thing that turns a
   *  clean interface into a busy one. */
  hairline: string;
  /** A softer hairline for dividers inside a card. */
  hairlineSoft: string;

  ink: string;
  inkSoft: string;
  inkMuted: string;
  /** Text on top of the accent. */
  onPrimary: string;

  primary: string;
  primaryPressed: string;
  /** A wash of the accent, for selected rows and quiet emphasis. */
  primarySoft: string;
  /** Readable text on primarySoft. */
  onPrimarySoft: string;

  success: string;
  successSoft: string;
  warning: string;
  warningSoft: string;
  danger: string;
  dangerPressed: string;
  dangerSoft: string;

  /** The translucent fill behind the bottom navigation, over the blur. */
  glass: string;
  /** The single hairline that separates the glass bar from the content. */
  glassEdge: string;
  /** Scrim behind a modal or sheet. */
  scrim: string;
  /** The one shadow colour in the system. */
  shadow: string;
}

/**
 * Light.
 *
 * Not white. `#FAF7F3` is a warm off-white that makes a true white card read as
 * raised without needing a shadow to say so, which is where most of the
 * cleanliness in this design comes from.
 */
export const lightPalette: Palette = {
  ground: '#FAF7F3',
  surface: '#FFFFFF',
  surfaceSunk: '#F3EEE7',
  surfaceRaised: '#FAF7F3',
  hairline: '#E8E0D6',
  hairlineSoft: '#F0EAE2',

  ink: '#1A1512',
  inkSoft: '#4B4139',
  inkMuted: '#73665B',
  onPrimary: '#FFFFFF',

  primary: '#B54A22',
  primaryPressed: '#983D1B',
  primarySoft: '#FBEDE5',
  onPrimarySoft: '#8A3616',

  success: '#1C7A4E',
  successSoft: '#E4F3EA',
  warning: '#96620C',
  warningSoft: '#FBF0DC',
  danger: '#B33124',
  dangerPressed: '#8F271C',
  dangerSoft: '#FBEAE7',

  glass: 'rgba(250, 247, 243, 0.72)',
  glassEdge: 'rgba(26, 21, 18, 0.07)',
  scrim: 'rgba(26, 21, 18, 0.32)',
  shadow: '#1A1512',
};

/**
 * Dark.
 *
 * Deliberately designed rather than inverted. Three things differ beyond the
 * obvious swap:
 *
 * 1. The ground is a warm near-black rather than pure black, so the warmth of
 *    the brand survives the mode change instead of going grey.
 * 2. The accent is *lighter* than its light-mode counterpart, not darker. A
 *    saturated sienna on a dark ground is unreadable, so dark mode gets its own
 *    accent that happens to be the same hue.
 * 3. Text on the accent flips to a near-black, because white on a light orange
 *    fails contrast in exactly the way that is easy to miss.
 */
export const darkPalette: Palette = {
  ground: '#14110E',
  surface: '#1E1A16',
  surfaceSunk: '#272220',
  surfaceRaised: '#272220',
  hairline: '#332C27',
  hairlineSoft: '#2A2521',

  ink: '#F6F1EB',
  inkSoft: '#CFC5BA',
  inkMuted: '#9C9086',
  onPrimary: '#241009',

  primary: '#F0794A',
  primaryPressed: '#D96538',
  primarySoft: '#33201A',
  onPrimarySoft: '#F5A183',

  success: '#4FBF87',
  successSoft: '#152B21',
  warning: '#E3A44F',
  warningSoft: '#2E2415',
  danger: '#F0776A',
  dangerPressed: '#D25B4F',
  dangerSoft: '#33191A',

  glass: 'rgba(20, 17, 14, 0.62)',
  glassEdge: 'rgba(246, 241, 235, 0.10)',
  scrim: 'rgba(0, 0, 0, 0.55)',
  shadow: '#000000',
};

/** 4pt base scale. Nothing off the scale. */
export const spacing = {
  xxs: 2,
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
  chip: 10,
  control: 14,
  card: 18,
  sheet: 28,
  pill: 999,
} as const;

/** An eight step scale. Hierarchy comes from weight and size, not extra families. */
export const fontSizes = {
  micro: 11,
  caption: 13,
  footnote: 15,
  body: 16,
  callout: 18,
  title3: 21,
  title2: 26,
  title1: 32,
  display: 40,
} as const;

export const fontWeights = {
  regular: '400',
  medium: '500',
  semibold: '600',
  bold: '700',
} as const;

export const lineHeights = {
  micro: 15,
  caption: 18,
  footnote: 21,
  body: 24,
  callout: 26,
  title3: 27,
  title2: 32,
  title1: 38,
  display: 46,
} as const;

/**
 * Negative tracking on the large sizes only.
 *
 * Big type set at default tracking looks loose and amateurish; body type set
 * tight looks cramped and hurts reading. So the two are treated differently
 * rather than one value being applied everywhere.
 */
export const tracking = {
  display: -1.1,
  title1: -0.8,
  title2: -0.5,
  title3: -0.3,
  body: 0,
  caption: 0.1,
  /** Section headers are the one place small type is tracked out. */
  overline: 0.7,
} as const;

/**
 * Elevation.
 *
 * Two levels and no more. A card that needs a shadow to be distinguishable from
 * its background is a card whose background is wrong, so these are used for
 * things that genuinely float: the bottom bar and a sheet.
 */
export const elevation = {
  none: {
    shadowOpacity: 0,
    elevation: 0,
  },
  /** Barely there. Lifts a card off the ground without announcing itself. */
  low: {
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 1,
  },
  /** For things that genuinely float above content. */
  high: {
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.1,
    shadowRadius: 20,
    elevation: 10,
  },
} as const;

/** One border width. */
export const borders = {
  hairline: 1,
  /** For a selected control, where the border itself carries the state. */
  selected: 2,
} as const;

/**
 * Motion stays between 120 and 260ms with no overshoot bounce. Anything longer
 * reads as sluggish on the mid-range Android hardware most customers carry.
 */
export const motion = {
  instant: 120,
  fast: 160,
  base: 200,
  slow: 260,
} as const;

/** The minimum touch target we ship, in points. */
export const MIN_TOUCH_TARGET = 44;

/** How much room the floating bottom bar needs above safe-area inset. */
export const TAB_BAR_HEIGHT = 60;

export type Spacing = typeof spacing;
export type Radii = typeof radii;
