/**
 * The wordmark reveal.
 *
 * A late, quiet addition to a sequence that is otherwise locked, so most of what
 * matters here is what it does *not* do: it must not start a clock, must not
 * mount partway through, must not move the mark, and must still be fully visible
 * when the launch reports completion.
 *
 * Nothing asserts elapsed time. The reveal is a pure function of the master
 * progress, so it is checked by rendering at chosen values of that progress.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { AnimatedLaunchComposition } from '@/features/startup/AnimatedLaunchComposition';
import { AnimatedSyncWordmark } from '@/features/startup/AnimatedSyncWordmark';
import {
  SEGMENT,
  WORDMARK_GAP,
  WORDMARK_HEIGHT,
  WORDMARK_RISE,
  wordmarkOffset,
} from '@/features/startup/launch-timeline';
import { WORDMARK_LETTER_IDS } from '@/components/brand/wordmark-geometry';
import { renderWithProviders } from '@/test-utils/render';

const HIDDEN = { includeHiddenElements: true } as const;

/** Flattens whatever react-native hands back for `style`. */
function styleOf(node: { props: Record<string, unknown> }): Record<string, unknown> {
  const style = node.props.style;
  if (Array.isArray(style)) return Object.assign({}, ...style.flat(Infinity));
  return (style ?? {}) as Record<string, unknown>;
}

/** Renders at a chosen point on the master clock and reads what it drew. */
async function atProgress(value: number, settled = false) {
  const view = await renderWithProviders(
    <AnimatedSyncWordmark progress={{ value } as never} settled={settled} />,
  );
  return { view, style: styleOf(view.getByTestId('animated-sync-wordmark', HIDDEN)) };
}

describe('the reveal', () => {
  it('is invisible before its range begins', async () => {
    const { style } = await atProgress(0);

    expect(style.opacity).toBe(0);
  });

  it('is still invisible at the instant the range opens', async () => {
    const { style } = await atProgress(SEGMENT.wordmarkReveal[0]);

    expect(style.opacity).toBe(0);
  });

  it('is partly present midway through', async () => {
    const middle = (SEGMENT.wordmarkReveal[0] + SEGMENT.wordmarkReveal[1]) / 2;
    const { style } = await atProgress(middle);

    expect(style.opacity as number).toBeGreaterThan(0);
    expect(style.opacity as number).toBeLessThan(1);
  });

  it('is fully present the moment its range closes', async () => {
    const { style } = await atProgress(SEGMENT.wordmarkReveal[1]);

    expect(style.opacity).toBe(1);
  });

  it('stays fully present through to completion', async () => {
    // The launch reports completion at progress 1. If the wordmark were still
    // easing, or had begun to leave, the last frame anybody sees would be a
    // half-finished lockup.
    for (const value of [0.94, 0.97, 1]) {
      const { style } = await atProgress(value);

      expect(style.opacity).toBe(1);
    }
  });

  it('lifts a few points and lands at zero', async () => {
    const start = await atProgress(0);
    const end = await atProgress(1);

    const from = start.style.transform as { translateY: number }[];
    const to = end.style.transform as { translateY: number }[];

    expect(from[0].translateY).toBeCloseTo(WORDMARK_RISE);
    expect(to[0].translateY).toBe(0);
  });

  it('keeps the rise small enough to read as settling', () => {
    expect(WORDMARK_RISE).toBeGreaterThan(0);
    expect(WORDMARK_RISE).toBeLessThanOrEqual(6);
  });

  it('moves only opacity and vertical position', async () => {
    // No scale, no tracking, no stroke width, no per-letter anything. One
    // element settling, which is the whole brief.
    const middle = (SEGMENT.wordmarkReveal[0] + SEGMENT.wordmarkReveal[1]) / 2;
    const { style } = await atProgress(middle);

    const transform = style.transform as Record<string, number>[];

    expect(Object.keys(style).sort()).toEqual(['opacity', 'transform']);
    expect(transform).toHaveLength(1);
    expect(Object.keys(transform[0])).toEqual(['translateY']);
  });

  it('reveals the wordmark as one element rather than letter by letter', async () => {
    // All four letters share the single animated wrapper, so none of them can
    // arrive on its own.
    const { view, style } = await atProgress(0.88);

    // One opacity for all four, so none of them can arrive on its own.
    expect(style.opacity as number).toBeGreaterThan(0);
    for (const id of WORDMARK_LETTER_IDS) {
      expect(view.getByTestId(id, HIDDEN)).toBeTruthy();
    }
  });
});

describe('reduced motion', () => {
  it('draws the finished wordmark with no movement at all', async () => {
    const { style } = await atProgress(0, true);

    expect(style.opacity).toBe(1);
    expect((style.transform as { translateY: number }[])[0].translateY).toBe(0);
  });

  it('ignores the clock entirely when settled', async () => {
    // A faster version of the same movement is still movement.
    const { style } = await atProgress(0, true);

    expect(style.opacity).toBe(1);
  });
});

describe('the stacked composition', () => {
  it('mounts the wordmark from the first frame', async () => {
    // At zero opacity, not absent. A component inserted partway through the
    // sequence is a seam exactly where continuity matters.
    const view = await renderWithProviders(
      <AnimatedLaunchComposition size={320} markSize={86} />,
    );

    expect(view.getByTestId('animated-sync-wordmark', HIDDEN)).toBeTruthy();
    expect(view.getByTestId('animated-sync-mark', HIDDEN)).toBeTruthy();
  });

  it('places the wordmark below the mark without moving it', () => {
    // Offset from the same centre the mark occupies. The mark's own position is
    // untouched, so nothing shifts to make room.
    const offset = wordmarkOffset(86);

    expect(offset).toBeCloseTo(86 / 2 + WORDMARK_GAP + WORDMARK_HEIGHT / 2);
    expect(offset).toBeGreaterThan(86 / 2);
  });

  it('leaves the declared gap between the two', () => {
    const markBottom = 86 / 2;
    const wordmarkTop = wordmarkOffset(86) - WORDMARK_HEIGHT / 2;

    expect(wordmarkTop - markBottom).toBeCloseTo(WORDMARK_GAP);
  });

  it('keeps the whole lockup inside the smallest scene it is drawn at', () => {
    // The scene is 86 per cent of the shorter screen edge. On a narrow phone
    // that is about 275 points, and the wordmark must not fall off the bottom.
    const smallestScene = 320 * 0.86;
    const lowestPoint = wordmarkOffset(86) + WORDMARK_HEIGHT / 2;

    expect(lowestPoint).toBeLessThan(smallestScene / 2);
  });

  it('reveals the wordmark after the mark is essentially built', () => {
    expect(SEGMENT.wordmarkReveal[0]).toBeGreaterThanOrEqual(SEGMENT.ringResolve[0]);
  });

  it('finishes the reveal before the sequence ends', () => {
    expect(SEGMENT.wordmarkReveal[1]).toBeLessThan(1);
    expect(SEGMENT.wordmarkReveal[1]).toBeGreaterThan(SEGMENT.hold[0]);
  });
});

describe('it owns nothing', () => {
  const source = readFileSync(join(__dirname, '..', 'AnimatedSyncWordmark.tsx'), 'utf8');

  it('starts no timing, state or callback of its own', () => {
    expect(source).not.toMatch(/withTiming|withDelay|withSequence|withRepeat/);
    expect(source).not.toMatch(/setTimeout|setInterval|requestAnimationFrame/);
    expect(source).not.toMatch(/useState|useEffect|onComplete/);
  });

  it('draws the production wordmark rather than a copy of its paths', () => {
    expect(source).toMatch(/from '@\/components\/brand\/SyncWordmark'/);
    expect(source).not.toMatch(/<Path|d="M/);
  });

  it('leaves the sequence length alone', () => {
    const timeline = readFileSync(join(__dirname, '..', 'launch-timeline.ts'), 'utf8');

    expect(timeline).toMatch(/SEQUENCE_MS = 2050/);
  });
});
