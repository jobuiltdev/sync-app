/**
 * The dispatch map.
 *
 * An orientation tool, not a navigation one. It answers "where is this and how
 * far am I", and then hands off to the phone's maps application, which is
 * better at everything after that.
 *
 * ### Camera
 *
 * The region is computed once from whatever points exist and passed as
 * `initialRegion`, never as a controlled `region` prop. A controlled region
 * fights the user: every pan triggers a state update which re-asserts the
 * camera, and the map springs back under their finger. Re-framing happens only
 * when the set of points genuinely changes, and only through an explicit
 * animation the user asked for.
 *
 * ### Markers
 *
 * Two, visually distinct in shape as well as colour, because a provider
 * glancing at a map in daylight should not have to distinguish two similar pins
 * by hue. The map is never the only carrier of this information: the address
 * and the distance are text on the screen beneath it.
 */

import { memo, useEffect, useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import MapView, { Marker, PROVIDER_DEFAULT } from 'react-native-maps';

import { Icon } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { type Coordinate, type Region, regionFor } from '@/features/location/geo';
import { useTheme } from '@/theme/theme';
import { radii } from '@/theme/tokens';

interface JobMapProps {
  job: Coordinate;
  provider?: Coordinate | null;
  /** Named for the screen reader, which cannot read a map. */
  label: string;
  height?: number;
  /** Interaction is disabled for the small preview on a customer booking. */
  interactive?: boolean;
}

function JobMapView({ job, provider, label, height = 200, interactive = true }: JobMapProps) {
  const { palette, scheme } = useTheme();
  const mapRef = useRef<MapView | null>(null);

  const points = provider ? [job, provider] : [job];
  const initial = regionFor(points) as Region;

  // Re-frames only when the provider's position first arrives, which is the one
  // moment the interesting area genuinely changes. Keyed on the coordinate
  // rather than run on every render, so panning is never interrupted.
  const key = provider ? `${provider.latitude},${provider.longitude}` : 'none';
  const framed = useRef(key);

  useEffect(() => {
    if (framed.current === key) return;
    framed.current = key;

    const next = regionFor(provider ? [job, provider] : [job]);
    if (next) mapRef.current?.animateToRegion(next, 400);
  }, [key, job, provider]);

  return (
    <View
      style={[styles.frame, { height, borderColor: palette.hairline }]}
      // The map's contents are unreadable to assistive technology, so the
      // container carries the meaning and the text beneath it carries the rest.
      accessible
      accessibilityRole="image"
      accessibilityLabel={label}
    >
      <MapView
        ref={mapRef}
        provider={PROVIDER_DEFAULT}
        style={StyleSheet.absoluteFill}
        initialRegion={initial}
        // Native map styling is left alone. Forcing a warm tint over a map
        // costs legibility of the one thing a map is for, and both platforms
        // already follow the system appearance sensibly.
        userInterfaceStyle={scheme}
        scrollEnabled={interactive}
        zoomEnabled={interactive}
        rotateEnabled={false}
        pitchEnabled={false}
        toolbarEnabled={false}
        showsUserLocation={false}
        showsMyLocationButton={false}
        showsCompass={false}
        // Points of interest are noise on a dispatch map: the only places that
        // matter are already marked.
        showsPointsOfInterest={false}
      >
        <Marker coordinate={job} tracksViewChanges={false} title={label}>
          <View style={styles.pin}>
            <View style={[styles.pinHead, { backgroundColor: palette.primary }]}>
              <Icon name="pin" size={15} color={palette.onPrimary} strokeWidth={2.2} />
            </View>
            <View style={[styles.pinTail, { borderTopColor: palette.primary }]} />
          </View>
        </Marker>

        {provider ? (
          <Marker coordinate={provider} tracksViewChanges={false} title="You">
            {/* A dot, not a pin. Different shape as well as different colour,
                so the two are told apart without relying on hue. */}
            <View style={[styles.dotHalo, { backgroundColor: palette.glassEdge }]}>
              <View style={[styles.dot, { backgroundColor: palette.ink, borderColor: palette.surface }]} />
            </View>
          </Marker>
        ) : null}
      </MapView>
    </View>
  );
}

/** Memoised on the coordinates. A parent re-rendering for an unrelated reason
 *  must not remount a native map view. */
export const JobMap = memo(JobMapView, (prev, next) => {
  return (
    prev.job.latitude === next.job.latitude &&
    prev.job.longitude === next.job.longitude &&
    prev.provider?.latitude === next.provider?.latitude &&
    prev.provider?.longitude === next.provider?.longitude &&
    prev.height === next.height &&
    prev.label === next.label &&
    prev.interactive === next.interactive
  );
});

/** Shown where a map would be when the booking has no pinned coordinates. */
export function MapUnavailable({ children }: { children: string }) {
  const { palette } = useTheme();

  return (
    <View
      style={[
        styles.frame,
        styles.empty,
        { backgroundColor: palette.surfaceSunk, borderColor: palette.hairline },
      ]}
    >
      <Icon name="pin" size={22} color={palette.inkMuted} />
      <Text variant="caption" tone="muted" center>
        {children}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    borderRadius: radii.card,
    overflow: 'hidden',
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  empty: { height: 120, alignItems: 'center', justifyContent: 'center', gap: 8, padding: 16 },
  pin: { alignItems: 'center' },
  pinHead: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pinTail: {
    width: 0,
    height: 0,
    borderLeftWidth: 5,
    borderRightWidth: 5,
    borderTopWidth: 7,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    marginTop: -1,
  },
  dotHalo: { padding: 6, borderRadius: 999 },
  dot: { width: 15, height: 15, borderRadius: 8, borderWidth: 3 },
});
