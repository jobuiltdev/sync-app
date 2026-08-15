/**
 * Empty, error and blocked states.
 *
 * Three rules hold here, and they are the difference between an app that feels
 * finished and one that feels like a prototype:
 *
 * 1. **No blank screens.** Every list that can be empty says so, says why, and
 *    offers the thing the person should do next.
 * 2. **Never "Something went wrong" when the API said something better.** The
 *    backend returns a single error envelope with a human message and a stable
 *    code. Replacing that with a generic apology throws away the only useful
 *    information in the failure.
 * 3. **A failure the person can act on gets an action.** Retry for a network
 *    blip, a route for a missing prerequisite.
 */

import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { Icon, type IconName } from '@/components/ui/Icon';
import { IconPlate } from '@/components/ui/Pill';
import { Text } from '@/components/ui/Text';
import { Card } from '@/components/ui/Surface';
import { isNetworkError, messageFor } from '@/api/errors';
import { usePalette } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

/** A calm, centred state for an empty list. */
export function EmptyState({
  icon = 'briefcase',
  title,
  body,
  action,
}: {
  icon?: IconName;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <View style={styles.centred} accessibilityRole="summary">
      <IconPlate icon={icon} tone="neutral" size={56} />
      <View style={styles.centredText}>
        <Text variant="title3" center>
          {title}
        </Text>
        {body ? (
          <Text variant="footnote" tone="muted" center>
            {body}
          </Text>
        ) : null}
      </View>
      {action ? <View style={styles.action}>{action}</View> : null}
    </View>
  );
}

/**
 * A failure, with whatever the server actually said.
 *
 * A dropped connection is separated from a refusal because they are different
 * problems with different answers: one is worth retrying immediately, the other
 * usually is not.
 */
export function ErrorState({
  error,
  onRetry,
  retrying = false,
}: {
  error: unknown;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  const offline = isNetworkError(error);

  return (
    // `accessible` as well as the role: without it this is a container of
    // separate nodes, and a screen reader reads the parts without ever
    // announcing that something failed.
    <View style={styles.centred} accessible accessibilityRole="alert">
      <IconPlate icon={offline ? 'wifiOff' : 'alert'} tone={offline ? 'neutral' : 'danger'} size={56} />
      <View style={styles.centredText}>
        <Text variant="title3" center>
          {offline ? 'No connection' : 'That did not work'}
        </Text>
        <Text variant="footnote" tone="muted" center>
          {offline
            ? 'Check your data or Wi-Fi and try again.'
            : messageFor(error)}
        </Text>
      </View>
      {onRetry ? (
        <View style={styles.action}>
          <Button
            label="Try again"
            variant="secondary"
            icon="refresh"
            loading={retrying}
            onPress={onRetry}
            fullWidth={false}
          />
        </View>
      ) : null}
    </View>
  );
}

/**
 * An inline failure, for a form or a card.
 *
 * Carries the server's message verbatim. Errors are announced to assistive
 * technology so a screen reader user is not left waiting on a form that
 * silently refused.
 */
export function InlineError({ error, style }: { error: unknown; style?: object }) {
  const palette = usePalette();
  if (!error) return null;

  return (
    <Card tone="danger" padding="tight" style={style}>
      <View style={styles.inline}>
        <Icon name="alert" size={17} color={palette.danger} />
        <Text variant="footnote" style={{ color: palette.danger, flex: 1 }} accessibilityRole="alert">
          {isNetworkError(error)
            ? 'No connection. Check your data or Wi-Fi and try again.'
            : messageFor(error)}
        </Text>
      </View>
    </Card>
  );
}

/** A quiet confirmation. */
export function SuccessNote({ children }: { children: string }) {
  const palette = usePalette();

  return (
    <Card tone="success" padding="tight">
      <View style={styles.inline}>
        <Icon name="check" size={17} color={palette.success} strokeWidth={2.2} />
        <Text variant="footnote" style={{ color: palette.success, flex: 1 }}>
          {children}
        </Text>
      </View>
    </Card>
  );
}

/**
 * A prerequisite the person has not met yet.
 *
 * Not an error. Phone verification before booking is a rule of the product, and
 * presenting it as a failure makes the product look broken rather than careful.
 */
export function BlockedState({
  title,
  body,
  action,
  icon = 'shield',
}: {
  title: string;
  body: string;
  action?: ReactNode;
  icon?: IconName;
}) {
  return (
    <Card tone="warning">
      <View style={styles.blocked}>
        <IconPlate icon={icon} tone="warning" size={40} />
        <View style={styles.blockedText}>
          <Text variant="body" weight="semibold">
            {title}
          </Text>
          <Text variant="footnote" tone="soft">
            {body}
          </Text>
        </View>
      </View>
      {action ? <View style={styles.blockedAction}>{action}</View> : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  centred: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.lg,
    paddingVertical: spacing.xxl,
    paddingHorizontal: spacing.lg,
  },
  centredText: { gap: spacing.xs, alignItems: 'center' },
  action: { alignItems: 'center' },
  inline: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
  blocked: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  blockedText: { flex: 1, gap: spacing.xxs },
  blockedAction: { marginTop: spacing.md },
});
