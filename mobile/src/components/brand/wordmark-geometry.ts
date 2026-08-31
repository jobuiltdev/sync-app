/**
 * The Sync wordmark, as numbers.
 *
 * Uppercase SYNC, drawn as four monoline paths on a 69 by 20.7 grid. Every
 * coordinate is authored here so the component, the exported assets and any
 * future lockup all read one source, exactly as the Dual Route mark does.
 *
 * ### Why strokes rather than filled outlines
 *
 * The mark is a monoline: 7 units of stroke with round caps and joins. A
 * wordmark built from filled outlines beside it would be a second drawing
 * language on the same lockup, and the join between a filled letter and a
 * stroked mark is the kind of mismatch that makes a brand look assembled from
 * two sources.
 *
 * Stroking also makes even weight a property of the geometry rather than
 * something to be checked: there is one width, and no amount of editing an
 * anchor can make one part of a letter heavier than another.
 *
 * These are outlines in the sense that matters. There is no `<text>` element,
 * no font is loaded, and nothing depends on what is installed on the device.
 *
 * ### Weight
 *
 * Stroke 3 against a cap height of 17, so 1:5.67. The mark runs about 1:4.6.
 * The wordmark is deliberately the lighter of the two: it names the thing, the
 * mark is the thing, and a wordmark that matches the mark's weight competes
 * with it at exactly the sizes where the mark has to win.
 *
 * ### Optical corrections
 *
 * `S` and `C` overshoot the cap line and the baseline by 0.35, which is 2.1 per
 * cent of cap height. Round letters set to the same measured height as flat ones
 * read smaller, because they only touch the line at a point while `N` meets it
 * across a full stroke. The overshoot is what makes all four look the same size.
 *
 * Spacing is optical rather than equal. Ink gaps run 4.2, 3.4 and 4.8: `Y` is
 * tucked tighter on both sides because its diagonals open a large counter at the
 * baseline on the left and at the cap line on the right, and the round back of
 * `C` takes a wider gap from the flat stem of `N` than two flats would need.
 * Equal gaps here would read as SY NC.
 */

/** Everything below is authored against this box. */
export const WORDMARK_VIEWBOX = { width: 69, height: 20.7 } as const;

/** Width over height, for sizing from either dimension without distortion. */
export const WORDMARK_ASPECT = WORDMARK_VIEWBOX.width / WORDMARK_VIEWBOX.height;

/** One weight, everywhere. */
export const WORDMARK_STROKE_WIDTH = 3;

/** Where the flat letters sit. The round ones overshoot both by `OVERSHOOT`. */
export const CAP_LINE = 1.85;
export const BASELINE = 18.85;
export const OVERSHOOT = 0.35;

export interface WordmarkLetter {
  /** Stable across the component and every exported asset. */
  id: 'letter-s' | 'letter-y' | 'letter-n' | 'letter-c';
  letter: 'S' | 'Y' | 'N' | 'C';
  d: string;
  /** Ink extents including the stroke, which is what spacing is judged on. */
  ink: { left: number; right: number };
}

/**
 * The four letters, in reading order.
 *
 * `S` and `C` are built from cubics whose handles are collinear across every
 * interior join, so both measure a 0.000 degree tangent break end to end. That
 * is not decoration: a break of even a couple of degrees in a bowl this size
 * shows up as a flat spot at the sizes this has to survive.
 *
 * `Y` and `N` are straight runs. `Y` is one path in two subpaths, arms and stem,
 * because a single pen stroke cannot draw it without doubling back.
 */
export const WORDMARK_LETTERS: WordmarkLetter[] = [
  {
    id: 'letter-s',
    letter: 'S',
    // Six cubics, point symmetric about (7, 10.35). The symmetry is what stops
    // the two bowls disagreeing, which is the usual way a monoline S goes wrong.
    d:
      'M12.5 5.35C12.5 2.96 10.5 1.5 7 1.5C3.5 1.5 1.5 2.96 1.5 5.35' +
      'C1.5 7.75 3.5 8.79 7 10.35C10.5 11.91 12.5 12.95 12.5 15.35' +
      'C12.5 17.74 10.5 19.2 7 19.2C3.5 19.2 1.5 17.74 1.5 15.35',
    ink: { left: 0, right: 14 },
  },
  {
    id: 'letter-y',
    letter: 'Y',
    // Arms then stem. They meet at (25.7, 9.85), a shade above the optical
    // centre, because a junction placed at true centre reads as low.
    d: 'M19.7 1.85L25.7 9.85L31.7 1.85M25.7 9.85V18.85',
    ink: { left: 18.2, right: 33.2 },
  },
  {
    id: 'letter-n',
    letter: 'N',
    // One continuous run: up the left stem, down the diagonal, up the right.
    d: 'M38.1 18.85V1.85L49.1 18.85V1.85',
    ink: { left: 36.6, right: 50.6 },
  },
  {
    id: 'letter-c',
    letter: 'C',
    // Four cubics. The aperture faces right and the terminals are cut on the
    // curve's own tangent rather than horizontally, which keeps it from reading
    // as an incomplete O.
    d:
      'M67.4 4.73C66.2 2.44 64.5 1.5 62.4 1.5C59.3 1.5 56.9 5.46 56.9 10.35' +
      'C56.9 15.24 59.3 19.2 62.4 19.2C64.5 19.2 66.2 18.26 67.4 15.97',
    ink: { left: 55.4, right: 68.9 },
  },
];

/**
 * The wordmark's own colours.
 *
 * Deliberately not `palette.ink`. The body ink is `#1A1512` and `#F6F1EB`, which
 * are tuned for long-form reading against the app's surfaces; a wordmark sitting
 * on a plain ground wants the full contrast of the opposite ground, so these are
 * the two ground values swapped. The difference is small and it is the
 * difference between a logo that looks printed and one that looks typed.
 *
 * The mark keeps its own brand colour. The wordmark is not a second accent.
 */
export const WORDMARK_COLOR = {
  light: '#14110E',
  dark: '#FAF7F3',
  black: '#000000',
  white: '#FFFFFF',
} as const;

/** Every addressable piece, for tests and for the exported assets. */
export const WORDMARK_LETTER_IDS = WORDMARK_LETTERS.map((letter) => letter.id);
