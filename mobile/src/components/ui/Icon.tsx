/**
 * The Sync icon set.
 *
 * Drawn here rather than pulled from an icon font. Two reasons, and the second
 * is the real one:
 *
 * 1. An icon font ships several megabytes of glyphs to use fifteen of them.
 * 2. Material and Ionicons look like Material and Ionicons. A marketplace that
 *    wants its own visual identity cannot borrow the icon language of every
 *    other app on the phone and then claim a distinctive one.
 *
 * Every glyph is on a 24 unit grid, stroked rather than filled, with one weight
 * and round caps. Consistency across the set matters far more than the
 * cleverness of any single icon: mismatched stroke weights are the single most
 * common thing that makes an interface look unfinished.
 */

import Svg, { Circle, Path, Rect } from 'react-native-svg';

import { usePalette } from '@/theme/theme';

export type IconName =
  // navigation
  | 'home'
  | 'activity'
  | 'profile'
  // movement and chrome
  | 'chevronRight'
  | 'chevronLeft'
  | 'chevronDown'
  | 'close'
  | 'check'
  | 'plus'
  | 'arrowRight'
  | 'search'
  // meaning
  | 'clock'
  | 'pin'
  | 'wallet'
  | 'bank'
  | 'briefcase'
  | 'bell'
  | 'shield'
  | 'card'
  | 'alert'
  | 'info'
  | 'sun'
  | 'moon'
  | 'device'
  | 'logout'
  | 'star'
  | 'refresh'
  | 'wifiOff'
  // service categories
  | 'dispatch'
  | 'cleaning'
  | 'errands'
  | 'handyman'
  | 'beauty'
  | 'laundry';

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
  /** Filled icons are used only for the active navigation state. */
  strokeWidth?: number;
}

export function Icon({ name, size = 22, color, strokeWidth = 1.75 }: IconProps) {
  const palette = usePalette();
  const stroke = color ?? palette.ink;

  const common: Common = {
    stroke,
    strokeWidth,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    fill: 'none',
  };

  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {glyph(name, common)}
    </Svg>
  );
}

type Common = {
  stroke: string;
  strokeWidth: number;
  strokeLinecap: 'round';
  strokeLinejoin: 'round';
  fill: 'none';
};

function glyph(name: IconName, c: Common) {
  switch (name) {
    case 'home':
      return <Path d="M3.6 10.2 12 3.8l8.4 6.4V19a1.4 1.4 0 0 1-1.4 1.4H5a1.4 1.4 0 0 1-1.4-1.4Z" {...c} />;

    case 'activity':
      // A pulse rather than a list. Activity here is things in motion, and a
      // list icon would read as a settings menu.
      return <Path d="M3 12.5h4.2l2.4-6.2 4.1 11.4 2.3-5.2H21" {...c} />;

    case 'profile':
      return (
        <>
          <Circle cx={12} cy={8.4} r={3.6} {...c} />
          <Path d="M4.8 20.2a7.4 7.4 0 0 1 14.4 0" {...c} />
        </>
      );

    case 'chevronRight':
      return <Path d="m9.5 5.5 6.4 6.5-6.4 6.5" {...c} />;

    case 'chevronLeft':
      return <Path d="m14.5 5.5-6.4 6.5 6.4 6.5" {...c} />;

    case 'chevronDown':
      return <Path d="m5.5 9.5 6.5 6.4 6.5-6.4" {...c} />;

    case 'close':
      return (
        <>
          <Path d="m6.2 6.2 11.6 11.6" {...c} />
          <Path d="M17.8 6.2 6.2 17.8" {...c} />
        </>
      );

    case 'check':
      return <Path d="m4.8 12.6 4.8 4.8L19.2 7.4" {...c} />;

    case 'plus':
      return (
        <>
          <Path d="M12 5v14" {...c} />
          <Path d="M5 12h14" {...c} />
        </>
      );

    case 'arrowRight':
      return (
        <>
          <Path d="M4.5 12h15" {...c} />
          <Path d="m13.4 5.9 6.1 6.1-6.1 6.1" {...c} />
        </>
      );

    case 'search':
      return (
        <>
          <Circle cx={11} cy={11} r={6.4} {...c} />
          <Path d="m15.8 15.8 3.7 3.7" {...c} />
        </>
      );

    case 'clock':
      return (
        <>
          <Circle cx={12} cy={12} r={8.4} {...c} />
          <Path d="M12 7.4V12l3.2 2" {...c} />
        </>
      );

    case 'pin':
      return (
        <>
          <Path d="M12 21c4.2-4.2 6.3-7.4 6.3-10a6.3 6.3 0 0 0-12.6 0c0 2.6 2.1 5.8 6.3 10Z" {...c} />
          <Circle cx={12} cy={10.8} r={2.4} {...c} />
        </>
      );

    case 'wallet':
      return (
        <>
          <Rect x={3.2} y={6.2} width={17.6} height={12.6} rx={2.6} {...c} />
          <Path d="M3.2 10.4h17.6" {...c} />
          <Circle cx={16.6} cy={14.6} r={1.15} {...c} />
        </>
      );

    case 'bank':
      return (
        <>
          <Path d="M3.4 9.6 12 4.6l8.6 5" {...c} />
          <Path d="M5.6 9.6v8.2M10 9.6v8.2M14 9.6v8.2M18.4 9.6v8.2" {...c} />
          <Path d="M3.4 19.6h17.2" {...c} />
        </>
      );

    case 'briefcase':
      return (
        <>
          <Rect x={3.2} y={7.6} width={17.6} height={11.4} rx={2.4} {...c} />
          <Path d="M9 7.6V6.2A1.6 1.6 0 0 1 10.6 4.6h2.8A1.6 1.6 0 0 1 15 6.2v1.4" {...c} />
        </>
      );

    case 'bell':
      return (
        <>
          <Path d="M6.4 10.4a5.6 5.6 0 0 1 11.2 0c0 3.4.9 5 1.8 6H4.6c.9-1 1.8-2.6 1.8-6Z" {...c} />
          <Path d="M10.2 19.8a2 2 0 0 0 3.6 0" {...c} />
        </>
      );

    case 'shield':
      return (
        <>
          <Path d="M12 3.6 5.4 6.2v5.2c0 4 2.7 7.3 6.6 8.8 3.9-1.5 6.6-4.8 6.6-8.8V6.2Z" {...c} />
          <Path d="m9.2 12 2 2 3.6-3.8" {...c} />
        </>
      );

    case 'card':
      return (
        <>
          <Rect x={2.8} y={5.4} width={18.4} height={13.2} rx={2.6} {...c} />
          <Path d="M2.8 10h18.4" {...c} />
        </>
      );

    case 'alert':
      return (
        <>
          <Path d="M12 4.4 2.9 19.4h18.2Z" {...c} />
          <Path d="M12 10v3.6" {...c} />
          <Path d="M12 16.6v.1" {...c} />
        </>
      );

    case 'info':
      return (
        <>
          <Circle cx={12} cy={12} r={8.4} {...c} />
          <Path d="M12 11v5" {...c} />
          <Path d="M12 8v.1" {...c} />
        </>
      );

    case 'sun':
      return (
        <>
          <Circle cx={12} cy={12} r={4} {...c} />
          <Path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" {...c} />
        </>
      );

    case 'moon':
      return <Path d="M20 13.6A8.2 8.2 0 0 1 10.4 4a8.4 8.4 0 1 0 9.6 9.6Z" {...c} />;

    case 'device':
      return (
        <>
          <Rect x={2.8} y={4.6} width={18.4} height={12} rx={2.2} {...c} />
          <Path d="M8.4 19.8h7.2" {...c} />
        </>
      );

    case 'logout':
      return (
        <>
          <Path d="M14.4 4.6H6.8a2 2 0 0 0-2 2v10.8a2 2 0 0 0 2 2h7.6" {...c} />
          <Path d="M18.8 12H9.6" {...c} />
          <Path d="m15.6 8.8 3.2 3.2-3.2 3.2" {...c} />
        </>
      );

    case 'star':
      return (
        <Path
          d="m12 4.4 2.4 4.9 5.4.8-3.9 3.8.9 5.3-4.8-2.5-4.8 2.5.9-5.3-3.9-3.8 5.4-.8Z"
          {...c}
        />
      );

    case 'refresh':
      return (
        <>
          <Path d="M19.4 12a7.4 7.4 0 1 1-2.2-5.3" {...c} />
          <Path d="M19.6 4.6v4.2h-4.2" {...c} />
        </>
      );

    case 'wifiOff':
      return (
        <>
          <Path d="M4 4.2 20 20.2" {...c} />
          <Path d="M8.2 13.4a5.6 5.6 0 0 1 3-1.5" {...c} />
          <Path d="M4.8 9.8a10.6 10.6 0 0 1 4-2.4" {...c} />
          <Path d="M15.8 13.4a5.6 5.6 0 0 0-1.6-1.1" {...c} />
          <Path d="M19.2 9.8a10.6 10.6 0 0 0-5.4-2.7" {...c} />
          <Path d="M12 18.2v.1" {...c} />
        </>
      );

    // --- service categories --------------------------------------------------
    // One per vertical, keyed off the catalog's `icon_key` with a neutral
    // fallback, so a seventh category added server-side renders sensibly
    // instead of rendering nothing.

    case 'dispatch':
      return (
        <>
          <Path d="M3.4 7.6 12 4.2l8.6 3.4v8.8L12 19.8l-8.6-3.4Z" {...c} />
          <Path d="M3.4 7.6 12 11l8.6-3.4" {...c} />
          <Path d="M12 11v8.8" {...c} />
        </>
      );

    case 'cleaning':
      return (
        <>
          <Path d="M8.6 3.8h3.2v6.4H8.6Z" {...c} />
          <Path d="M6.6 10.2h7.2l1.4 9.2a1 1 0 0 1-1 1.2H6.2a1 1 0 0 1-1-1.2Z" {...c} />
          <Path d="M17.4 5.6h3M17.4 9h2.2" {...c} />
        </>
      );

    case 'errands':
      return (
        <>
          <Path d="M5.4 8.2h13.2l-1 11a1.6 1.6 0 0 1-1.6 1.4H8a1.6 1.6 0 0 1-1.6-1.4Z" {...c} />
          <Path d="M9 8.2V6.6a3 3 0 0 1 6 0v1.6" {...c} />
        </>
      );

    case 'handyman':
      return (
        <>
          <Path d="M15.4 3.8a4.4 4.4 0 0 0-5.2 5.8L4 15.8a2 2 0 0 0 2.8 2.8l6.2-6.2a4.4 4.4 0 0 0 5.8-5.2l-2.6 2.6-2.4-.6-.6-2.4Z" {...c} />
        </>
      );

    case 'beauty':
      return (
        <>
          <Circle cx={6.6} cy={17.4} r={2.6} {...c} />
          <Circle cx={17.4} cy={17.4} r={2.6} {...c} />
          <Path d="m8.5 15.6 8.4-11.4M15.5 15.6 7.1 4.2" {...c} />
        </>
      );

    case 'laundry':
      return (
        <>
          <Path d="M8.4 3.8 5 5.6v4.2h2.4v9a1.4 1.4 0 0 0 1.4 1.4h6.4a1.4 1.4 0 0 0 1.4-1.4v-9H19V5.6l-3.4-1.8Z" {...c} />
          <Path d="M9.4 3.8a2.6 2.6 0 0 0 5.2 0" {...c} />
        </>
      );

    default:
      return <Circle cx={12} cy={12} r={8.4} {...c} />;
  }
}

/**
 * Which glyph a catalog category should show.
 *
 * Driven by the server's `icon_key`. Unknown keys fall back to a briefcase
 * rather than to nothing, so adding a category server-side never ships an
 * app update and never leaves a hole in the grid.
 */
const CATEGORY_ICONS: Record<string, IconName> = {
  dispatch: 'dispatch',
  cleaning: 'cleaning',
  errands: 'errands',
  home_services: 'handyman',
  'home-services': 'handyman',
  handyman: 'handyman',
  beauty: 'beauty',
  laundry: 'laundry',
};

export function categoryIcon(key: string): IconName {
  return CATEGORY_ICONS[key] ?? CATEGORY_ICONS[key?.toLowerCase?.()] ?? 'briefcase';
}
