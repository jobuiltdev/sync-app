/**
 * Where the job is, how far away it is, and how to drive there.
 *
 * Composed rather than built into the job screen, so the same block can appear
 * on a provider's job and (without the dispatch half) on a customer's booking.
 *
 * ### What the lifecycle changes
 *
 * Only the prominence, never the availability. A completed job keeps its map,
 * because "where was that" is a reasonable question about work you did last
 * week. What a cancelled or expired booking loses is the *navigation* actions,
 * because offering to drive somebody to a job that is not happening is the app
 * being wrong out loud. Whether a job is live comes from the server's status,
 * and no action here is derived from a local guess.
 */

import { useState } from 'react';
import { Alert, Linking, StyleSheet, View } from 'react-native';

import type { BookingAddress, BookingStatus } from '@/api/endpoints/bookings';
import { Button } from '@/components/ui/Button';
import { Icon } from '@/components/ui/Icon';
import { JobMap, MapUnavailable } from '@/components/map/JobMap';
import { Text } from '@/components/ui/Text';
import { Card } from '@/components/ui/Surface';
import { directionsFallbackUrl, directionsUrl } from '@/features/location/directions';
import {
  type Coordinate,
  describeDistance,
  distanceMetres,
  formatDistance,
  toCoordinate,
} from '@/features/location/geo';
import { locationStatusMessage, useDeviceLocation } from '@/features/location/hooks';
import { usePalette } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

/**
 * Statuses where driving somewhere is no longer a sensible offer.
 *
 * Read from the server's status, which is the only place a booking's state
 * lives. Everything else keeps its dispatch actions, including COMPLETED: a
 * provider revisiting a finished job may still want the address.
 */
const NOT_TRAVELLING: BookingStatus[] = ['CANCELLED', 'EXPIRED'];

/** Statuses where the journey is the thing the provider is doing right now. */
const TRAVELLING: BookingStatus[] = ['ASSIGNED', 'EN_ROUTE'];

interface DispatchSectionProps {
  address: BookingAddress;
  status: BookingStatus;
  reference: string;
  /** Customers get the map without the dispatch controls: no distance from a
   *  provider, no directions, because it is their own address. */
  variant?: 'provider' | 'customer';
}

export function DispatchSection({
  address,
  status,
  reference,
  variant = 'provider',
}: DispatchSectionProps) {
  const palette = usePalette();
  const device = useDeviceLocation();
  const [opening, setOpening] = useState(false);

  // The booking's snapshot, never the customer's live Address row. The address
  // was copied onto the booking when it was made, and editing the saved address
  // afterwards must not move a job that already happened.
  const job = toCoordinate(address.latitude, address.longitude);

  const where = [address.area, address.lga, address.state].filter(Boolean).join(', ');
  const isCustomer = variant === 'customer';
  const canTravel = !NOT_TRAVELLING.includes(status);
  const isTravelling = TRAVELLING.includes(status);

  const metres =
    job && device.coordinate ? distanceMetres(device.coordinate, job) : null;

  if (!job) {
    return (
      <MapUnavailable>
        {isCustomer
          ? 'This address has no map pin yet.'
          : 'This job has no map pin. Use the address and landmark below.'}
      </MapUnavailable>
    );
  }

  const openDirections = async () => {
    setOpening(true);
    const label = `${reference} ${address.landmark || address.street_address}`.trim();

    try {
      const url = directionsUrl(job, label);
      const supported = await Linking.canOpenURL(url);
      // A `geo:` intent with nothing registered throws, so the browser link is
      // the floor rather than an error dialog.
      await Linking.openURL(supported ? url : directionsFallbackUrl(job));
    } catch {
      Alert.alert(
        'No maps app',
        'We could not open a maps application on this device. The address is on this screen.',
      );
    } finally {
      setOpening(false);
    }
  };

  return (
    <View style={styles.section}>
      <JobMap
        job={job}
        provider={device.coordinate}
        // A map is opaque to a screen reader, so its accessible name carries
        // what it shows and the text below carries the detail.
        label={`Map showing the job at ${where || address.street_address}`}
        height={isTravelling ? 220 : 180}
        interactive={!isCustomer}
      />

      <View style={styles.summary}>
        <Icon name="pin" size={17} color={palette.inkMuted} />
        <View style={styles.summaryText}>
          <Text variant="footnote" weight="medium">
            {address.landmark || address.street_address}
          </Text>
          <Text variant="caption" tone="muted">
            {where}
          </Text>
        </View>

        {metres !== null ? (
          <Text
            variant="caption"
            weight="semibold"
            tone="primary"
            accessibilityLabel={describeDistance(metres)}
          >
            {formatDistance(metres)}
          </Text>
        ) : null}
      </View>

      {!isCustomer && canTravel ? (
        <View style={styles.actions}>
          {device.status === 'idle' || device.status === 'requesting' ? (
            <Button
              label="Show how far I am"
              variant="secondary"
              icon="pin"
              loading={device.status === 'requesting'}
              // Permission is asked for here and only here: on a tap, on a
              // dispatch screen, by somebody who wants the answer.
              onPress={() => void device.request()}
            />
          ) : null}

          <Button
            label="Get directions"
            variant={isTravelling ? 'primary' : 'secondary'}
            icon="arrowRight"
            loading={opening}
            onPress={() => void openDirections()}
          />
        </View>
      ) : null}

      {locationStatusMessage(device.status) ? (
        <Card padding="tight">
          <Text variant="caption" tone="muted">
            {locationStatusMessage(device.status)}
          </Text>
        </Card>
      ) : null}

      {metres !== null ? (
        <Text variant="caption" tone="muted">
          Straight-line distance, so the drive will be longer.
        </Text>
      ) : null}
    </View>
  );
}

export type { Coordinate };

const styles = StyleSheet.create({
  section: { gap: spacing.md },
  summary: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  summaryText: { flex: 1, gap: 1 },
  actions: { gap: spacing.sm },
});
