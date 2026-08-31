import Svg, { Circle, Path, type SvgProps } from 'react-native-svg';

import {
  MARK_VIEWBOX,
  NODE_LOWER,
  NODE_STROKE_WIDTH,
  NODE_UPPER,
  ROUTE_LOWER_PATH,
  ROUTE_STROKE_WIDTH,
  ROUTE_UPPER_PATH,
} from '@/components/brand/mark-geometry';
import { usePalette } from '@/theme/theme';

export interface SyncMarkProps extends Omit<SvgProps, 'color' | 'height' | 'width'> {
  color?: string;
  size?: number;
}

export function SyncMark({ color, size = 64, ...props }: SyncMarkProps) {
  const palette = usePalette();
  const stroke = color ?? palette.primary;

  return (
    <Svg
      accessibilityLabel="Sync"
      accessibilityRole="image"
      fill="none"
      height={size}
      viewBox={`0 0 ${MARK_VIEWBOX} ${MARK_VIEWBOX}`}
      width={size}
      {...props}
    >
      <Path
        id="route-upper"
        testID="sync-route-upper"
        d={ROUTE_UPPER_PATH}
        stroke={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={ROUTE_STROKE_WIDTH}
      />
      <Path
        id="route-lower"
        testID="sync-route-lower"
        d={ROUTE_LOWER_PATH}
        stroke={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={ROUTE_STROKE_WIDTH}
      />
      <Circle
        id="node-upper"
        testID="sync-node-upper"
        cx={NODE_UPPER.cx}
        cy={NODE_UPPER.cy}
        r={NODE_UPPER.r}
        stroke={stroke}
        strokeWidth={NODE_STROKE_WIDTH}
      />
      <Circle
        id="node-lower"
        testID="sync-node-lower"
        cx={NODE_LOWER.cx}
        cy={NODE_LOWER.cy}
        r={NODE_LOWER.r}
        stroke={stroke}
        strokeWidth={NODE_STROKE_WIDTH}
      />
    </Svg>
  );
}
