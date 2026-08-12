import { StyleSheet, Text, View } from 'react-native';

import { type BookingStatus, statusLabel } from '@/api/endpoints/bookings';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/** Booking status as a pill. Status is never conveyed by colour alone: the label
 *  says what the colour means, so it survives a colour vision deficiency. */
export function StatusPill({ status }: { status: BookingStatus }) {
  const tone =
    status === 'COMPLETED'
      ? styles.success
      : status === 'CANCELLED'
        ? styles.muted
        : styles.active;

  return (
    <View style={[styles.pill, tone]}>
      <Text style={styles.text}>{statusLabel(status)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    borderRadius: radii.pill,
    alignSelf: 'flex-start',
  },
  active: { backgroundColor: colors.accentSoft },
  success: { backgroundColor: colors.accentSoft },
  muted: { backgroundColor: colors.surfaceSunk },
  text: { fontSize: fontSizes.caption, fontWeight: fontWeights.medium, color: colors.inkSoft },
});
