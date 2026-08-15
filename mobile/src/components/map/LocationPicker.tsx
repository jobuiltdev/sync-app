/**
 * Putting a pin on an address.
 *
 * This is the piece that makes the whole dispatch map worth having. Coordinates
 * have been storable since M1 and nothing ever wrote one, so every booking
 * snapshot carried a null pair and any map built on them would have been empty
 * forever.
 *
 * ### Why current location leads
 *
 * Most people save an address while standing in it: moving into a flat, at the
 * office, at their mother's house. One tap beats dragging a pin across Lagos on
 * a phone screen. The map is still there to correct it, because GPS indoors can
 * be fifty metres out and the person knows which building is theirs.
 *
 * Optional throughout. An address with no pin is still a perfectly good address
 * with a landmark on it, which is how the app worked until now, and blocking
 * somebody from saving one because the sky is cloudy would be absurd.
 */

import { useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import MapView, { Marker, PROVIDER_DEFAULT, type MapPressEvent } from 'react-native-maps';

import { Button } from '@/components/ui/Button';
import { Icon } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { type Coordinate, regionFor } from '@/features/location/geo';
import { locationStatusMessage, useDeviceLocation } from '@/features/location/hooks';
import { useTheme } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

/** Lagos, for the rare case where somebody opens the map with no fix and no
 *  pin. Better than the middle of the Atlantic, which is where 0,0 is. */
const DEFAULT_REGION = {
  latitude: 6.5244,
  longitude: 3.3792,
  latitudeDelta: 0.12,
  longitudeDelta: 0.12,
};

interface LocationPickerProps {
  value: Coordinate | null;
  onChange: (coordinate: Coordinate | null) => void;
}

export function LocationPicker({ value, onChange }: LocationPickerProps) {
  const { palette, scheme } = useTheme();
  const device = useDeviceLocation();
  const mapRef = useRef<MapView | null>(null);
  const [expanded, setExpanded] = useState(false);

  /**
   * Asks for a fix and adopts whatever comes back.
   *
   * Done in the handler rather than in an effect watching `device.coordinate`,
   * so the pin moves exactly once per tap. An effect would also re-adopt the
   * stale fix on any later render and drag the pin back from wherever the
   * person had just placed it.
   */
  const pickCurrentLocation = async () => {
    const fix = await device.request();
    if (!fix) return;

    onChange(fix);
    setExpanded(true);
    mapRef.current?.animateToRegion(regionFor([fix]) ?? DEFAULT_REGION, 350);
  };

  const region = value ? (regionFor([value]) ?? DEFAULT_REGION) : DEFAULT_REGION;

  return (
    <View style={styles.wrapper}>
      <View style={styles.head}>
        <Text variant="footnote" weight="medium" tone="soft">
          Map pin
        </Text>
        <Text variant="caption" tone="muted">
          Optional
        </Text>
      </View>

      <Button
        label={value ? 'Update to my current location' : 'Use my current location'}
        variant={value ? 'ghost' : 'secondary'}
        icon="pin"
        loading={device.status === 'requesting'}
        // The only place an address form asks for location, and only on a tap.
        onPress={() => void pickCurrentLocation()}
      />

      {value || expanded ? (
        <View style={[styles.frame, { borderColor: palette.hairline }]}>
          <MapView
            ref={mapRef}
            provider={PROVIDER_DEFAULT}
            style={StyleSheet.absoluteFill}
            initialRegion={region}
            userInterfaceStyle={scheme}
            rotateEnabled={false}
            pitchEnabled={false}
            toolbarEnabled={false}
            showsPointsOfInterest={false}
            // Tapping the map moves the pin, which is a more forgiving target
            // than dragging a small marker with a thumb.
            onPress={(event: MapPressEvent) => onChange(event.nativeEvent.coordinate)}
          >
            {value ? (
              <Marker
                coordinate={value}
                draggable
                tracksViewChanges={false}
                onDragEnd={(event) => onChange(event.nativeEvent.coordinate)}
                title="This address"
              >
                <View style={styles.pin}>
                  <View style={[styles.pinHead, { backgroundColor: palette.primary }]}>
                    <Icon name="pin" size={15} color={palette.onPrimary} strokeWidth={2.2} />
                  </View>
                  <View style={[styles.pinTail, { borderTopColor: palette.primary }]} />
                </View>
              </Marker>
            ) : null}
          </MapView>
        </View>
      ) : null}

      {value ? (
        <View style={styles.footer}>
          <Text variant="caption" tone="muted" style={styles.grow}>
            Tap or drag the pin to correct it.
          </Text>
          <Button
            label="Remove pin"
            variant="ghost"
            size="compact"
            fullWidth={false}
            onPress={() => onChange(null)}
          />
        </View>
      ) : (
        <Text variant="caption" tone="muted">
          A pin helps your provider find you. You can save the address without one.
        </Text>
      )}

      {locationStatusMessage(device.status) ? (
        <Text variant="caption" tone="muted">
          {locationStatusMessage(device.status)}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { gap: spacing.sm },
  head: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  frame: {
    height: 180,
    borderRadius: radii.card,
    overflow: 'hidden',
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  footer: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  grow: { flex: 1 },
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
});
