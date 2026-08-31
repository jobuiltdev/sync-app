import Svg, { Circle, Path } from 'react-native-svg';

import {
  NETWORK_INDICATOR,
  NETWORK_NODES,
  NETWORK_ROUTES,
  NETWORK_VIEWBOX,
} from '@/features/startup/network-geometry';
import { usePalette } from '@/theme/theme';

/**
 * The launch scene behind the Sync mark.
 *
 * Four service nodes, three curved routes and one indicator, arranged around a
 * reserved centre where the mark sits. Eight drawn elements, which is the whole
 * budget: the point is to suggest a network operating around you, and past
 * roughly a dozen shapes that impression turns into visual noise and, later,
 * into dropped frames.
 *
 * ### Static, deliberately and permanently
 *
 * Every coordinate comes from `network-geometry` as a literal. Nothing is
 * measured, derived or recomputed, at any size. That is not just tidiness: the
 * animation that follows will move these elements with transforms and stroke
 * offsets, and the one thing that reliably ruins an SVG animation is rebuilding
 * path data on every frame.
 *
 * Responsiveness is the viewBox doing its job. One fixed 320 unit square scaled
 * to whatever square the parent gives it, so a small iPhone and a large Android
 * get the same composition at different scales rather than a different
 * composition.
 *
 * ### Colour
 *
 * Two tokens and no invented ones. `primary` carries the two routes that arrive
 * at the mark and the nodes anchoring them; `inkMuted` carries the rest.
 *
 * The quiet geometry was originally drawn in `hairline`, which is tuned to
 * separate a card from its background and all but vanished as a line on the
 * light ground. It now uses the muted ink at reduced opacity instead: dark
 * enough to read on both grounds, held back far enough that it stays scenery.
 * Opacity rather than a lighter colour, so the same value works in light and
 * dark without a second token.
 *
 * No gradient, no shadow, no glow: every one of those is a per-pixel cost at
 * launch, and this composition is meant to be nearly free.
 */

export interface LaunchNetworkProps {
  /** Side of the square the scene is drawn into. */
  size: number;
}

export function LaunchNetwork({ size }: LaunchNetworkProps) {
  const palette = usePalette();

  const colour = { primary: palette.primary, quiet: palette.inkMuted };

  /** A filled dot reads considerably stronger than an outline of the same size,
   *  so the quiet ones are held back further than they were as rings. */
  const nodeOpacity = { primary: 1, quiet: 0.55 };

  return (
    <Svg
      testID="launch-network"
      // Decorative. The mark beside it already carries the accessible name, and
      // announcing an abstract network to a screen reader would be noise.
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      fill="none"
      height={size}
      pointerEvents="none"
      viewBox={`0 0 ${NETWORK_VIEWBOX} ${NETWORK_VIEWBOX}`}
      width={size}
    >
      {/* Routes first so nodes and the indicator sit on top of them. */}
      {NETWORK_ROUTES.map((route) => (
        <Path
          key={route.id}
          id={route.id}
          testID={route.id}
          d={route.d}
          stroke={colour[route.emphasis]}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeOpacity={route.opacity}
          strokeWidth={route.width}
        />
      ))}

      {NETWORK_NODES.map((node) => (
        <Circle
          key={node.id}
          id={node.id}
          testID={node.id}
          cx={node.cx}
          cy={node.cy}
          // Filled, not stroked. Ringed endpoints are how the Sync mark
          // terminates its own routes, and repeating that shape around the
          // network diluted the one place it carries meaning.
          fill={colour[node.emphasis]}
          fillOpacity={nodeOpacity[node.emphasis]}
          r={node.r}
        />
      ))}

      {/* Small and filled. It is told apart from a node by moving, not by being
          larger; a big dot on a thin route reads as a bead on a wire. */}
      <Circle
        id={NETWORK_INDICATOR.id}
        testID={NETWORK_INDICATOR.id}
        cx={NETWORK_INDICATOR.cx}
        cy={NETWORK_INDICATOR.cy}
        fill={palette.primary}
        r={NETWORK_INDICATOR.r}
      />
    </Svg>
  );
}
