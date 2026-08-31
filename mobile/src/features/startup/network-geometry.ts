/**
 * The launch network, as numbers.
 *
 * A fixed 320 unit square that scales to whatever the screen gives it. Every
 * coordinate is authored here and nothing is computed at runtime, which is what
 * lets the scene animate later without recalculating a single path: the future
 * work is transforms and stroke offsets over geometry that never changes.
 *
 * ### What this composition is trying to do
 *
 * The first attempt read as an umbrella: one dominant arch across the top with
 * two routes hanging off it, all the weight above the mark and nothing drawing
 * the eye inward. This is the correction, and the organising idea is different.
 *
 * Two routes **arrive** at the mark from opposite corners, and they are aimed:
 * each one ends pointing at the centre, on the same diagonal the Sync mark's own
 * routes occupy. The mark's upper route enters from its top right and its lower
 * route leaves at its bottom left, so `route-arrival` comes down from the upper
 * right and `route-approach` comes up from the lower left. When the scene later
 * animates into the mark, those two are already travelling along the lines the
 * `S` is about to be drawn on.
 *
 * The third route is context. It links the two quiet nodes around the outside
 * and crosses `route-approach` once, at about a hundred degrees, which reads as
 * two roads meeting rather than as a drawing error.
 *
 * Nodes occupy all four quadrants at unequal distances from the centre, so the
 * arrangement cannot be mistaken for a compass rose or a ring.
 *
 * It is deliberately not a map. No pins, no streets, no district shapes.
 */

/** Everything below is expressed against this square. */
export const NETWORK_VIEWBOX = 320;

/**
 * Radius kept clear in the middle for the Sync mark.
 *
 * Raised from 62 when the mark grew past 76 points, and left there when the mark
 * came back down to 86. The mark is drawn on top of this scene by `SyncMark` or
 * `AnimatedSyncMark`, never by the network, so the two are positioned and
 * animated independently. On the smallest phone the scene shrinks to about 275
 * points, where an 86 point mark spans roughly 100 units of this viewBox: a 70
 * unit radius leaves clear air around it with room to spare.
 */
export const CENTRE = { x: 160, y: 160, clearRadius: 70 } as const;

export interface NetworkNode {
  id: string;
  cx: number;
  cy: number;
  r: number;
  /** Primary nodes anchor the two routes that arrive at the mark. The rest are
   *  scenery and are drawn in a quieter token. */
  emphasis: 'primary' | 'quiet';
}

/**
 * Four nodes, one per quadrant.
 *
 * The two primary nodes sit on the upper-right and lower-left diagonal, which is
 * the axis the mark itself is built on, and share a radius of 133: that pairing
 * is deliberate, and it is what makes the two arriving routes feel like a matched
 * pair rather than an accident. The two quiet ones sit off that axis at 107 and
 * 119, and those unequal radii are what stop the set reading as a ring.
 *
 * All four are at least 54 units inside the frame. The scene is scaled to fit
 * rather than cropped, so this is belt and braces, but a node clipped in half on
 * a short phone looks like a rendering bug rather than a design.
 *
 * They are drawn as small filled dots rather than as outlined rings. The rings
 * were both too heavy for scenery and, worse, a repetition: ringed endpoints are
 * how the Sync mark terminates its own two routes, and echoing that shape four
 * times around the mark diluted the one place it means something.
 */
export const NETWORK_NODES: NetworkNode[] = [
  { id: 'node-a', cx: 250, cy: 62, r: 4.25, emphasis: 'primary' },
  { id: 'node-b', cx: 64, cy: 252, r: 4.25, emphasis: 'primary' },
  { id: 'node-c', cx: 70, cy: 102, r: 3.75, emphasis: 'quiet' },
  { id: 'node-d', cx: 256, cy: 230, r: 3.75, emphasis: 'quiet' },
];

export interface NetworkRoute {
  id: string;
  d: string;
  emphasis: 'primary' | 'quiet';
  width: number;
  /** Quiet geometry is drawn in a muted token at reduced opacity rather than in
   *  the hairline colour, which all but disappeared on the light ground. */
  opacity: number;
}

/**
 * Three routes.
 *
 * Both primary routes end **aimed at the centre**, within ten degrees, so the
 * eye is carried inward rather than left drifting along a curve. Both enter the
 * frame on a shallow diagonal and then turn in, which is the same move the mark
 * itself makes: its upper route arrives almost horizontally before curving down,
 * and its lower route straightens out again as it leaves. These two rehearse
 * that shape at a larger scale.
 *
 * They were previously near-straight: measured against the chord between their
 * own endpoints they deviated by 9.5 and 2.8 units, which is why they read as
 * diagonal slashes. They now bow by 19.9 and 21.2, curving in opposite
 * directions, with different entry angles and different bow distribution along
 * their length, so neither is a mirror of the other.
 *
 * Both were also checked for waviness. An earlier version of `route-approach`
 * reversed its curvature three times over its length, which at this stroke width
 * reads as a wobble rather than as a road; the shipped curve turns consistently
 * in one direction from end to end.
 *
 * ### Tangent continuity at the nodes
 *
 * Each primary route is two cubics meeting at its own primary node, and in the
 * first version the handles either side of that join were not collinear: the
 * incoming and outgoing tangents broke by 55 degrees on `route-arrival` and 30
 * on `route-approach`. Those are real corners, and on a recording they showed as
 * elbows exactly where the node sits, which reads as a fault in the drawing
 * rather than as a bend in a road.
 *
 * Only the control handles changed. Start points, node coordinates and inward
 * endpoints are all as they were, so the composition, the clearance and the
 * crossing with `route-context` are untouched. The residual break is now 1.1 and
 * 0.6 degrees, which is below what the eye resolves at this stroke width, and a
 * test holds both joins to it.
 *
 * The corrected handles also leave each route running **horizontally** at its
 * inward end: the upper one travelling left, the lower one travelling right.
 * That is deliberate. It is the direction each one has to continue in when it
 * becomes the corresponding Sync route, and `MARK_ENTRY` in `launch-timeline`
 * matches it.
 */
export const NETWORK_ROUTES: NetworkRoute[] = [
  {
    // In from beyond the top-right corner, through the upper-right node, then
    // turning down and in. Ends on the diagonal where the mark's upper route
    // begins.
    id: 'route-arrival',
    d: 'M352 24C318 37 282 45 250 62C232 72 228 108 212 108',
    emphasis: 'primary',
    width: 2.5,
    opacity: 1,
  },
  {
    // Its opposite number, not its mirror: in from beyond the left edge, through
    // the lower-left node, ending where the mark's lower route finishes. Enters
    // at a shallower angle and bows slightly harder than `route-arrival`.
    id: 'route-approach',
    d: 'M-24 292C28 278 48 278 64 252C73 237 92 212 108 212',
    emphasis: 'primary',
    width: 2.5,
    opacity: 1,
  },
  {
    // Context. Links the two quiet nodes, and the shape is the whole point of
    // this revision.
    //
    // It used to be a single smooth sweep around the bottom left. Measured, that
    // curve never once reversed its curvature and held a radius of 107 to 153
    // about the centre: a constant-radius arc with no inflection is, precisely,
    // an orbit, which is exactly how it read.
    //
    // This one changes direction. It leaves the upper-left node heading inward
    // and down, reverses to swing out and away, turns a near right-angle corner
    // at the bottom, then straightens as it climbs to the lower-right node. One
    // genuine curvature reversal and four separate bends, so no part of it can
    // be continued into a circle. Its distance from the centre now ranges from
    // 77 to 158, nearly double the old variation, which is what stops the eye
    // reading a ring.
    //
    // It crosses `route-approach` once, at about a hundred degrees, which reads
    // as two roads meeting rather than as a drawing error.
    id: 'route-context',
    d: 'M70 102C86 132 86 156 80 178C70 214 44 230 52 266C60 300 118 308 160 294C200 280 234 262 256 230',
    emphasis: 'quiet',
    width: 1.4,
    opacity: 0.55,
  },
];

/**
 * A single indicator, on the inward run of `route-arrival`.
 *
 * Deliberately not at the apex of a curve, where it read as a bead threaded on
 * a wire. Sitting between the node and the mark, on the stretch that is visibly
 * heading inward, it reads instead as something moving toward Sync, which is
 * exactly what it will later be.
 *
 * Its position is that segment evaluated by hand at t=0.65 and rounded: whole
 * units are imperceptible at this scale and keep the constant readable.
 *
 * Small on purpose. It is told apart from a node by the fact that it moves, not
 * by being bigger than one; a large dot travelling a thin route reads as a bead
 * on a wire.
 */
export const NETWORK_INDICATOR = { id: 'route-indicator', cx: 228, cy: 90, r: 3 } as const;

/** Every addressable piece of the scene, for tests and for the animation work
 *  that follows. */
export const NETWORK_ELEMENT_IDS = [
  ...NETWORK_ROUTES.map((route) => route.id),
  ...NETWORK_NODES.map((node) => node.id),
  NETWORK_INDICATOR.id,
] as const;

/**
 * Arc length of each primary route, measured at authoring time.
 *
 * The formation consumes these routes with a dash, which needs to know how long
 * they are. Sampled offline rather than read back from a mounted node, for the
 * same reason none of the rest of this geometry is measured at runtime.
 */
export const ROUTE_LENGTH: Record<string, number> = {
  'route-arrival': 170.546,
  'route-approach': 160.958,
  'route-context': 413.318,
};

/**
 * The inward tip of each primary route, written out.
 *
 * These are the final coordinate of each path above, restated as numbers so the
 * convergence can aim at them without anybody parsing a `d` string at runtime. A
 * test samples both paths and asserts these still match, so the duplication
 * cannot rot.
 *
 * This is the end that points at the mark, and it is the end that later lands on
 * the corresponding Sync route endpoint.
 */
export const ROUTE_ENDPOINT: Record<string, { x: number; y: number }> = {
  'route-arrival': { x: 212, y: 108 },
  'route-approach': { x: 108, y: 212 },
};

/**
 * How far each primary route starts outside its final position.
 *
 * The network used to draw itself in, one path at a time, from zero length. That
 * reads as an illustration being sketched rather than as routes that already
 * exist. Now every route is a complete solid shape from its first visible frame
 * and arrives by moving a few units inward while fading up.
 *
 * Outward for each route means away from the mark along its own diagonal, which
 * is the direction it came from.
 */
export const ROUTE_ENTRY: Record<string, { x: number; y: number }> = {
  'route-arrival': { x: 9, y: -9 },
  'route-approach': { x: -9, y: 9 },
};

/**
 * Where the indicator travels, as pre-authored waypoints.
 *
 * Fourteen points sampled from the inward cubic of `route-arrival` at authoring
 * time, not at runtime: the animation walks between these literals and never
 * evaluates a bezier while it plays. That is the whole reason they exist.
 *
 * There were four, which was enough while the route had a corner in it and the
 * eye had something else to look at. Against a smooth curve four literals are a
 * visible polygon, so they were resampled: equally spaced by arc length, 4.73
 * units apart with a standard deviation of 0.05, and the resulting polyline
 * never sits further than 0.28 units from the real curve. At a 3 unit indicator
 * on a 2.5 unit route that is not resolvable.
 *
 * The journey starts on `node-a` and finishes at the route's inward end, which
 * is the point aimed at the mark. The static composition parks the indicator at
 * (228, 90), which is a shade over half way along this run.
 *
 * `node-a` itself travels these points during the launch. It used to sit still
 * while a separate indicator ran the same curve, which is two objects doing one
 * job; now the node is the thing that moves, and the standalone indicator is not
 * part of the animated composition at all.
 */
export const INDICATOR_JOURNEY = [
  { x: 250, y: 62 },
  { x: 246.1, y: 64.7 },
  { x: 242.8, y: 68 },
  { x: 239.8, y: 71.8 },
  { x: 237.2, y: 75.7 },
  { x: 234.9, y: 79.8 },
  { x: 232.7, y: 84 },
  { x: 230.5, y: 88.2 },
  { x: 228.3, y: 92.4 },
  { x: 226, y: 96.6 },
  { x: 223.4, y: 100.5 },
  { x: 220.4, y: 104.2 },
  { x: 216.6, y: 106.9 },
  { x: 212, y: 108 },
] as const;

/**
 * How far each primary route slides toward the centre as the network resolves.
 *
 * Small, and in opposite directions: `route-arrival` sits upper right of the
 * mark so inward is down and left, `route-approach` lower left so inward is up
 * and right. Expressed in viewBox units and applied as a transform, so no path
 * data changes.
 */
export const ROUTE_PULL: Record<string, { x: number; y: number }> = {
  'route-arrival': { x: -14, y: 14 },
  'route-approach': { x: 14, y: -14 },
};

/**
 * The lower stream's waypoints, the counterpart of `INDICATOR_JOURNEY`.
 *
 * Sampled the same way from the inward cubic of `route-approach`: fourteen
 * points, evenly spaced by arc length at 4.721 units with a standard deviation
 * of 0.045 over a 61.40 unit run.
 *
 * This exists because `node-b` was the one dot on screen that never moved. Every
 * other element had somewhere to be and it sat at the bend of its own route
 * while the route flowed past it, which is the single thing a recorded review
 * picks out fastest.
 */
export const LOWER_JOURNEY = [
  { x: 64, y: 252 },
  { x: 66.5, y: 248 },
  { x: 69.1, y: 244.1 },
  { x: 71.8, y: 240.2 },
  { x: 74.7, y: 236.4 },
  { x: 77.7, y: 232.8 },
  { x: 80.7, y: 229.2 },
  { x: 84, y: 225.7 },
  { x: 87.4, y: 222.5 },
  { x: 91, y: 219.4 },
  { x: 94.8, y: 216.7 },
  { x: 98.9, y: 214.3 },
  { x: 103.3, y: 212.7 },
  { x: 108, y: 212 },
] as const;

/**
 * A short drift along `route-context` for each quiet node.
 *
 * Thirty-four units, which is about eight percent of that route: enough that
 * neither dot is pinned while the scene moves around it, little enough that the
 * scenery stays scenery. `node-c` runs forward from the route's start and
 * `node-d` backward from its end, so both drift the same way relative to the
 * curve rather than one appearing to swim against it.
 *
 * Both recede by moving and shrinking rather than by opacity alone. A dot that
 * only dims looks switched off; one that pulls away and fades looks like it left.
 */
export const QUIET_DRIFT: Record<string, readonly { x: number; y: number }[]> = {
  'node-c': [
    { x: 70, y: 102 },
    { x: 73.8, y: 109.6 },
    { x: 77.1, y: 117.5 },
    { x: 79.8, y: 125.5 },
    { x: 81.8, y: 133.7 },
  ],
  'node-d': [
    { x: 256, y: 230 },
    { x: 251, y: 236.8 },
    { x: 245.5, y: 243.3 },
    { x: 239.6, y: 249.4 },
    { x: 233.3, y: 255.2 },
  ],
};
