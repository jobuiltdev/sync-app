/**
 * The Sync wordmark.
 *
 * Two things are worth protecting. The letterforms have to be genuinely smooth,
 * which at monoline weights means the handles either side of every interior join
 * must be collinear; a break of a couple of degrees inside a bowl shows as a
 * flat spot long before anybody can name what is wrong with it. And the exported
 * assets have to be the same drawing as the component, because a wordmark that
 * differs between the app and the files handed to anyone else is two wordmarks.
 *
 * Everything here is authoring-time analysis run against the shipped constants.
 * Nothing in the app parses a path.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { SyncWordmark } from '@/components/brand/SyncWordmark';
import {
  BASELINE,
  CAP_LINE,
  OVERSHOOT,
  WORDMARK_ASPECT,
  WORDMARK_COLOR,
  WORDMARK_LETTERS,
  WORDMARK_LETTER_IDS,
  WORDMARK_STROKE_WIDTH,
  WORDMARK_VIEWBOX,
} from '@/components/brand/wordmark-geometry';
import { renderWithProviders } from '@/test-utils/render';

interface Point {
  x: number;
  y: number;
}
type Cubic = [Point, Point, Point, Point];

/** Pulls the cubic segments out of a path, ignoring line and move commands. */
function cubicsOf(d: string): Cubic[] {
  const tokens = d.match(/[MCLVH]|-?\d+(?:\.\d+)?/g)!;
  const out: Cubic[] = [];
  let cursor: Point = { x: 0, y: 0 };
  let i = 0;

  while (i < tokens.length) {
    const command = tokens[i];
    if (command === 'M' || command === 'L') {
      cursor = { x: Number(tokens[i + 1]), y: Number(tokens[i + 2]) };
      i += 3;
    } else if (command === 'V') {
      cursor = { x: cursor.x, y: Number(tokens[i + 1]) };
      i += 2;
    } else if (command === 'H') {
      cursor = { x: Number(tokens[i + 1]), y: cursor.y };
      i += 2;
    } else if (command === 'C') {
      i += 1;
      while (i + 5 < tokens.length && !Number.isNaN(Number(tokens[i]))) {
        const n = tokens.slice(i, i + 6).map(Number);
        const end = { x: n[4], y: n[5] };
        out.push([cursor, { x: n[0], y: n[1] }, { x: n[2], y: n[3] }, end]);
        cursor = end;
        i += 6;
      }
    } else {
      i += 1;
    }
  }
  return out;
}

/** Every point a path visits, cubics and straight runs alike. */
function samplePath(d: string, per = 200): Point[] {
  const tokens = d.match(/[MCLVH]|-?\d+(?:\.\d+)?/g)!;
  const points: Point[] = [];
  let cursor: Point = { x: 0, y: 0 };
  let i = 0;

  const line = (to: Point) => {
    for (let k = 1; k <= per; k += 1) {
      points.push({
        x: cursor.x + (to.x - cursor.x) * (k / per),
        y: cursor.y + (to.y - cursor.y) * (k / per),
      });
    }
    cursor = to;
  };

  while (i < tokens.length) {
    const command = tokens[i];
    if (command === 'M') {
      cursor = { x: Number(tokens[i + 1]), y: Number(tokens[i + 2]) };
      points.push(cursor);
      i += 3;
    } else if (command === 'L') {
      line({ x: Number(tokens[i + 1]), y: Number(tokens[i + 2]) });
      i += 3;
    } else if (command === 'V') {
      line({ x: cursor.x, y: Number(tokens[i + 1]) });
      i += 2;
    } else if (command === 'H') {
      line({ x: Number(tokens[i + 1]), y: cursor.y });
      i += 2;
    } else if (command === 'C') {
      i += 1;
      while (i + 5 < tokens.length && !Number.isNaN(Number(tokens[i]))) {
        const n = tokens.slice(i, i + 6).map(Number);
        const [p0, c1, c2, p3] = [
          cursor,
          { x: n[0], y: n[1] },
          { x: n[2], y: n[3] },
          { x: n[4], y: n[5] },
        ];
        for (let k = 1; k <= per; k += 1) {
          const t = k / per;
          const u = 1 - t;
          points.push({
            x: u ** 3 * p0.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t ** 3 * p3.x,
            y: u ** 3 * p0.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t ** 3 * p3.y,
          });
        }
        cursor = p3;
        i += 6;
      }
    } else {
      i += 1;
    }
  }
  return points;
}

const byId = (id: string) => WORDMARK_LETTERS.find((letter) => letter.id === id)!;

/**
 * react-native-svg resolves a colour string into an opaque ARGB integer before
 * it reaches the rendered props, so comparing against the hex would always fail.
 */
const argb = (hex: string) => 0xff000000 + parseInt(hex.slice(1), 16);
const strokeOf = (node: { props: Record<string, unknown> }) =>
  (node.props.stroke as { payload: number }).payload;
const ROUND = ['letter-s', 'letter-c'];
const FLAT = ['letter-y', 'letter-n'];

describe('the letterforms', () => {
  it('spells SYNC in four separate paths', () => {
    expect(WORDMARK_LETTERS.map((letter) => letter.letter).join('')).toBe('SYNC');
    expect(WORDMARK_LETTER_IDS).toEqual(['letter-s', 'letter-y', 'letter-n', 'letter-c']);
  });

  it('curves smoothly through every interior join', () => {
    // The one that matters. Collinear handles either side of a join, or the bowl
    // has a flat spot in it.
    for (const id of ROUND) {
      const segments = cubicsOf(byId(id).d);

      for (let i = 1; i < segments.length; i += 1) {
        const incoming = segments[i - 1];
        const outgoing = segments[i];
        const before = {
          x: incoming[3].x - incoming[2].x,
          y: incoming[3].y - incoming[2].y,
        };
        const after = {
          x: outgoing[1].x - outgoing[0].x,
          y: outgoing[1].y - outgoing[0].y,
        };
        const cross =
          (before.x * after.y - before.y * after.x) /
          (Math.hypot(before.x, before.y) * Math.hypot(after.x, after.y));

        expect(Math.abs(cross)).toBeLessThan(0.01);
      }
    }
  });

  it('never doubles back at a join', () => {
    // Collinear and reversed is a cusp, which is a spike rather than a curve.
    for (const id of ROUND) {
      const segments = cubicsOf(byId(id).d);

      for (let i = 1; i < segments.length; i += 1) {
        const before = {
          x: segments[i - 1][3].x - segments[i - 1][2].x,
          y: segments[i - 1][3].y - segments[i - 1][2].y,
        };
        const after = {
          x: segments[i][1].x - segments[i][0].x,
          y: segments[i][1].y - segments[i][0].y,
        };
        const dot =
          (before.x * after.x + before.y * after.y) /
          (Math.hypot(before.x, before.y) * Math.hypot(after.x, after.y));

        expect(dot).toBeGreaterThan(0.99);
      }
    }
  });

  it('keeps the geometry economical', () => {
    // Few points, on purpose. Extra anchors in a monoline bowl are extra places
    // for it to go slightly wrong.
    expect(cubicsOf(byId('letter-s').d)).toHaveLength(6);
    expect(cubicsOf(byId('letter-c').d)).toHaveLength(4);
    expect(cubicsOf(byId('letter-y').d)).toHaveLength(0);
    expect(cubicsOf(byId('letter-n').d)).toHaveLength(0);
  });

  it('draws the S point symmetric about its own centre', () => {
    // The usual way a monoline S fails is one bowl slightly larger than the
    // other, which reads as a lean.
    const segments = cubicsOf(byId('letter-s').d);
    const centre = { x: 7, y: (CAP_LINE - OVERSHOOT + BASELINE + OVERSHOOT) / 2 };
    const anchors = [segments[0][0], ...segments.map((segment) => segment[3])];

    for (const anchor of anchors) {
      const mirrored = { x: 2 * centre.x - anchor.x, y: 2 * centre.y - anchor.y };
      const nearest = Math.min(
        ...anchors.map((other) => Math.hypot(other.x - mirrored.x, other.y - mirrored.y)),
      );

      expect(nearest).toBeLessThan(0.02);
    }
  });

  it('sits every letter on the same cap line and baseline', () => {
    for (const id of FLAT) {
      const ys = samplePath(byId(id).d).map((point) => point.y);

      expect(Math.min(...ys)).toBeCloseTo(CAP_LINE, 2);
      expect(Math.max(...ys)).toBeCloseTo(BASELINE, 2);
    }
  });

  it('overshoots the round letters so they read the same size', () => {
    // A round letter measured to the same height as a flat one looks smaller,
    // because it only touches the line at a point. Roughly two per cent of cap
    // height is the correction.
    for (const id of ROUND) {
      const ys = samplePath(byId(id).d).map((point) => point.y);

      expect(Math.min(...ys)).toBeCloseTo(CAP_LINE - OVERSHOOT, 2);
      expect(Math.max(...ys)).toBeCloseTo(BASELINE + OVERSHOOT, 2);
    }

    const capHeight = BASELINE - CAP_LINE;
    expect(OVERSHOOT / capHeight).toBeGreaterThan(0.01);
    expect(OVERSHOOT / capHeight).toBeLessThan(0.03);
  });

  it('fits every letter inside the viewBox', () => {
    // Ink, not centreline. A stroke clipped by the edge of the box is the sort
    // of thing that only shows up once it is on a background.
    const radius = WORDMARK_STROKE_WIDTH / 2;

    for (const letter of WORDMARK_LETTERS) {
      const points = samplePath(letter.d);
      const xs = points.map((point) => point.x);
      const ys = points.map((point) => point.y);

      expect(Math.min(...xs) - radius).toBeGreaterThanOrEqual(-0.01);
      expect(Math.max(...xs) + radius).toBeLessThanOrEqual(WORDMARK_VIEWBOX.width + 0.01);
      expect(Math.min(...ys) - radius).toBeGreaterThanOrEqual(-0.01);
      expect(Math.max(...ys) + radius).toBeLessThanOrEqual(WORDMARK_VIEWBOX.height + 0.01);
    }
  });

  it('declares ink extents that match the drawing', () => {
    // The spacing is judged on these, so they cannot be approximate.
    const radius = WORDMARK_STROKE_WIDTH / 2;

    for (const letter of WORDMARK_LETTERS) {
      const xs = samplePath(letter.d).map((point) => point.x);

      expect(Math.min(...xs) - radius).toBeCloseTo(letter.ink.left, 1);
      expect(Math.max(...xs) + radius).toBeCloseTo(letter.ink.right, 1);
    }
  });
});

describe('spacing', () => {
  const gaps = WORDMARK_LETTERS.slice(1).map(
    (letter, i) => letter.ink.left - WORDMARK_LETTERS[i].ink.right,
  );

  it('never lets two letters touch or collide', () => {
    for (const gap of gaps) {
      expect(gap).toBeGreaterThan(1.5);
    }
  });

  it('spaces optically rather than equally', () => {
    // Equal gaps around a Y read as SY NC, because its diagonals already open a
    // large counter at the baseline on one side and the cap line on the other.
    const equal = gaps.every((gap) => Math.abs(gap - gaps[0]) < 0.01);

    expect(equal).toBe(false);
  });

  it('tucks the Y tighter than the round back of the C', () => {
    const [sToY, yToN, nToC] = gaps;

    expect(yToN).toBeLessThan(sToY);
    expect(yToN).toBeLessThan(nToC);
  });

  it('keeps the tracking generous rather than set solid', () => {
    // A wordmark this short is set open. Anything under a stroke width of air
    // between letters would be a logotype, not a wordmark.
    for (const gap of gaps) {
      expect(gap).toBeGreaterThan(WORDMARK_STROKE_WIDTH);
    }
  });
});

describe('weight and proportion', () => {
  it('stays lighter than the Dual Route mark', () => {
    // The mark is the primary element. A wordmark at the same weight competes
    // with it at exactly the sizes where the mark has to win.
    const wordmarkRatio = (BASELINE - CAP_LINE) / WORDMARK_STROKE_WIDTH;
    // The mark's routes span roughly 32 units of its 64 box at stroke 7.
    const markRatio = 32 / 7;

    expect(wordmarkRatio).toBeGreaterThan(markRatio);
  });

  it('stays legible rather than hairline', () => {
    const ratio = (BASELINE - CAP_LINE) / WORDMARK_STROKE_WIDTH;

    expect(ratio).toBeLessThan(8);
  });

  it('is moderately wide rather than condensed', () => {
    expect(WORDMARK_ASPECT).toBeGreaterThan(3);
    expect(WORDMARK_ASPECT).toBeLessThan(4);
  });

  it('holds a stroke of at least half a point at the smallest intended size', () => {
    // Cut for 18 to 28 points tall. Below about half a point a stroke stops
    // resolving cleanly on a two times screen.
    const atSmallest = (18 / WORDMARK_VIEWBOX.height) * WORDMARK_STROKE_WIDTH;

    expect(atSmallest).toBeGreaterThan(2);
  });
});

describe('the component', () => {
  it('renders all four letters with stable ids', async () => {
    const view = await renderWithProviders(<SyncWordmark />);

    for (const id of WORDMARK_LETTER_IDS) {
      expect(view.getByTestId(id)).toBeTruthy();
    }
  });

  it('draws the same paths the constants declare', async () => {
    const view = await renderWithProviders(<SyncWordmark />);

    for (const letter of WORDMARK_LETTERS) {
      expect(view.getByTestId(letter.id).props.d).toBe(letter.d);
    }
  });

  it('uses one weight for every letter', async () => {
    const view = await renderWithProviders(<SyncWordmark />);

    for (const id of WORDMARK_LETTER_IDS) {
      expect(view.getByTestId(id).props.strokeWidth).toBe(WORDMARK_STROKE_WIDTH);
    }
  });

  it('takes its colour from the resolved scheme', async () => {
    const light = await renderWithProviders(<SyncWordmark />, { mode: 'light' });
    const dark = await renderWithProviders(<SyncWordmark />, { mode: 'dark' });

    expect(strokeOf(light.getByTestId('letter-s'))).toBe(argb(WORDMARK_COLOR.light));
    expect(strokeOf(dark.getByTestId('letter-s'))).toBe(argb(WORDMARK_COLOR.dark));
  });

  it('accepts a colour override', async () => {
    const view = await renderWithProviders(<SyncWordmark color={WORDMARK_COLOR.black} />);

    for (const id of WORDMARK_LETTER_IDS) {
      expect(strokeOf(view.getByTestId(id))).toBe(argb(WORDMARK_COLOR.black));
    }
  });

  it('draws in one colour whichever way it is asked', async () => {
    // One ink, by construction. No gradient, no second fill, nothing that only
    // works against a particular background.
    const view = await renderWithProviders(<SyncWordmark color={WORDMARK_COLOR.white} />);
    const strokes = new Set(WORDMARK_LETTER_IDS.map((id) => strokeOf(view.getByTestId(id))));

    expect(strokes.size).toBe(1);
    expect([...strokes][0]).toBe(argb(WORDMARK_COLOR.white));
  });

  it('sizes from a height without distorting', async () => {
    const view = await renderWithProviders(<SyncWordmark height={24} />);
    const svg = view.getByLabelText('Sync').props;

    expect(svg.height).toBe(24);
    expect(svg.width).toBeCloseTo(24 * WORDMARK_ASPECT, 5);
  });

  it('sizes from a width without distorting', async () => {
    const view = await renderWithProviders(<SyncWordmark width={69} />);
    const svg = view.getByLabelText('Sync').props;

    expect(svg.width).toBeCloseTo(69, 5);
    expect(svg.height).toBeCloseTo(69 / WORDMARK_ASPECT, 5);
  });

  it('cannot be stretched by passing both', async () => {
    // Height wins and width is derived, so a caller passing a mismatched box
    // gets a correctly proportioned wordmark rather than a squashed one.
    const view = await renderWithProviders(<SyncWordmark height={20} width={400} />);
    const svg = view.getByLabelText('Sync').props;

    expect(svg.height).toBe(20);
    expect(svg.width).toBeCloseTo(20 * WORDMARK_ASPECT, 5);
  });

  it('carries an accessible name and allows it to be replaced', async () => {
    const standard = await renderWithProviders(<SyncWordmark />);
    expect(standard.getByLabelText('Sync')).toBeTruthy();

    const named = await renderWithProviders(<SyncWordmark accessibilityLabel="Sync home" />);
    expect(named.getByLabelText('Sync home')).toBeTruthy();
  });

  it('passes other svg props through', async () => {
    const view = await renderWithProviders(<SyncWordmark testID="brand-wordmark" />);

    expect(view.getByTestId('brand-wordmark')).toBeTruthy();
  });

  it('uses no text element and loads no font', () => {
    const source = readFileSync(
      join(__dirname, '..', 'SyncWordmark.tsx'),
      'utf8',
    );

    expect(source).not.toMatch(/<Text|fontFamily|useFonts|loadAsync/);
  });
});

describe('the exported assets', () => {
  const brand = join(__dirname, '..', '..', '..', '..', 'assets', 'brand');
  const read = (name: string) => readFileSync(join(brand, name), 'utf8');

  const wordmarks = [
    'sync-wordmark.svg',
    'sync-wordmark-light.svg',
    'sync-wordmark-dark.svg',
    'sync-wordmark-mono-black.svg',
    'sync-wordmark-mono-white.svg',
  ];
  const lockups = ['sync-lockup-light.svg', 'sync-lockup-dark.svg'];

  it('ships every variant', () => {
    for (const name of [...wordmarks, ...lockups]) {
      expect(read(name)).toContain('<svg');
    }
  });

  it('cuts every asset from the same paths the component draws', () => {
    // The whole reason the geometry lives in one module. If these ever diverge,
    // the app and the files handed to anybody else are two different wordmarks.
    for (const name of [...wordmarks, ...lockups]) {
      const file = read(name);

      for (const letter of WORDMARK_LETTERS) {
        expect(file).toContain(letter.d);
      }
    }
  });

  it('keeps the letters separately addressable in the files too', () => {
    for (const name of [...wordmarks, ...lockups]) {
      const file = read(name);

      for (const id of WORDMARK_LETTER_IDS) {
        expect(file).toContain(`id="${id}"`);
      }
    }
  });

  it('uses the declared colour for each variant', () => {
    expect(read('sync-wordmark-light.svg')).toContain(`stroke="${WORDMARK_COLOR.light}"`);
    expect(read('sync-wordmark-dark.svg')).toContain(`stroke="${WORDMARK_COLOR.dark}"`);
    expect(read('sync-wordmark-mono-black.svg')).toContain(`stroke="${WORDMARK_COLOR.black}"`);
    expect(read('sync-wordmark-mono-white.svg')).toContain(`stroke="${WORDMARK_COLOR.white}"`);
  });

  it('leaves the canonical wordmark transparent', () => {
    // No background rect, so it can be dropped onto anything.
    expect(read('sync-wordmark.svg')).not.toContain('<rect');
  });

  it('gives the light and dark variants their grounds', () => {
    expect(read('sync-wordmark-light.svg')).toContain('fill="#FAF7F3"');
    expect(read('sync-wordmark-dark.svg')).toContain('fill="#14110E"');
  });

  it('leaves the monochrome pair transparent', () => {
    expect(read('sync-wordmark-mono-black.svg')).not.toContain('<rect');
    expect(read('sync-wordmark-mono-white.svg')).not.toContain('<rect');
  });

  it('keeps the mark on its own brand colour in the lockups', () => {
    // The wordmark is not a second accent, and the mark is not restated in ink.
    expect(read('sync-lockup-light.svg')).toContain('stroke="#B54A22"');
    expect(read('sync-lockup-dark.svg')).toContain('stroke="#F0794A"');
  });

  it('draws the mark in the lockups from its shipped geometry', () => {
    for (const name of lockups) {
      const file = read(name);

      expect(file).toContain('M47 12H31C20 12 13 20 13 30C13 39 20 44 29 44');
      expect(file).toContain('M28 27C40 27 49 34 49 43C49 52 42 55 32 55H17');
    }
  });

  it('adds no gradient, filter or texture anywhere', () => {
    for (const name of [...wordmarks, ...lockups]) {
      expect(read(name)).not.toMatch(/Gradient|filter|feGaussian|pattern|mask/i);
    }
  });

  it('uses no text element in any asset', () => {
    for (const name of [...wordmarks, ...lockups]) {
      expect(read(name)).not.toMatch(/<text/i);
    }
  });

  it('names every asset for assistive technology', () => {
    for (const name of [...wordmarks, ...lockups]) {
      expect(read(name)).toContain('role="img"');
      expect(read(name)).toContain('<title');
    }
  });
});
