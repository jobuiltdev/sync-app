import { useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import type { ChecklistItem, ProviderVerification } from '@/api/endpoints/providers';
import { Button } from '@/components/ui/Button';
import { Header } from '@/components/ui/Header';
import { Field } from '@/components/ui/Field';
import { Icon } from '@/components/ui/Icon';
import { ListRow, RowGroup } from '@/components/ui/ListRow';
import { Pill } from '@/components/ui/Pill';
import { Screen } from '@/components/ui/Screen';
import { SkeletonList } from '@/components/ui/Skeleton';
import { ErrorState, InlineError } from '@/components/ui/States';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { Text } from '@/components/ui/Text';
import {
  useResubmitVerification,
  useStartVerification,
  useVerificationAttempt,
  useVerificationChecklist,
  useVerificationHistory,
} from '@/features/providers/hooks';
import {
  STAGE_COPY,
  attemptStatusView,
  checkStatusView,
  rejectionMessage,
  verificationStage,
} from '@/features/providers/verification-presentation';
import { usePalette } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

/**
 * Identity verification, from the provider's side.
 *
 * The screen answers one question at a time: what is happening now, and what do
 * I do about it. Everything it renders is server state. **It computes no progress
 * of its own**, because a client that works out its own answer eventually
 * disagrees with the server about whether somebody may begin a paid check.
 *
 * ### What this screen cannot do
 *
 * It cannot approve anybody, and it has no control that would try. Approval is a
 * person's decision at the end of the queue; a clean external check reaches
 * `UNDER_REVIEW` and stops. The API refuses to accept a status, an outcome or a
 * review field, so there is no request this screen could make that would change
 * that even if a future edit tried.
 *
 * ### What it never handles
 *
 * No NIN, no BVN, no photograph, no document upload. The provider approves the
 * check at the identity provider and comes back with a reference; that reference
 * is sent once and never stored. What Sync keeps is the outcome, the vendor's
 * reference and four digits for support.
 */
export default function ProviderVerificationScreen() {
  const router = useRouter();
  const palette = usePalette();

  const checklist = useVerificationChecklist();
  const attempt = useVerificationAttempt();
  const history = useVerificationHistory();

  const start = useStartVerification();
  const resubmit = useResubmitVerification();

  // The only thing this screen holds locally. Everything else is the server's.
  const [reference, setReference] = useState('');

  if (checklist.isPending) {
    return (
      <Screen>
        <Header title="Identity verification" onBack={() => router.back()} />
        <SkeletonList rows={4} />
      </Screen>
    );
  }

  if (checklist.isError || !checklist.data) {
    return (
      <Screen>
        <Header title="Identity verification" onBack={() => router.back()} />
        <ErrorState error={checklist.error} onRetry={() => void checklist.refetch()} />
      </Screen>
    );
  }

  const board = checklist.data;
  // Three-valued on purpose, and passed through rather than flattened: an
  // attempt, null when the server has said there has never been one, undefined
  // while the query is still out. Collapsing the last two would make a provider
  // approved before verification existed look identical to one whose screen has
  // not finished loading.
  const latest = attempt.data;
  const stage = verificationStage(board, latest);
  const copy = STAGE_COPY[stage];
  const approvedWithoutCheck = stage === 'APPROVED_WITHOUT_CHECK';

  const busy = start.isPending || resubmit.isPending;

  const onStart = () => {
    start.mutate(
      { authorization_reference: reference.trim(), consent: true },
      { onSuccess: () => setReference('') },
    );
  };

  return (
    <Screen scroll>
      <Header title="Identity verification" onBack={() => router.back()} />

      <Card style={styles.intro}>
        <Text variant="title2">{copy.title}</Text>
        <Text variant="body" tone="muted" style={styles.introBody}>
          {copy.body}
        </Text>
        {latest ? (
          <Pill
            label={attemptStatusView(latest.status).label}
            tone={attemptStatusView(latest.status).tone}
            dot={attemptStatusView(latest.status).live}
            style={styles.introPill}
          />
        ) : null}
      </Card>

      {/* The server's checklist, rendered rather than recomputed. Titled for what
          it is in each case: for an approved provider with no attempt behind them
          nothing is "left", and heading it that way would invite them to chase
          two rows they cannot act on. */}
      <SectionHeader title={approvedWithoutCheck ? 'Your verification record' : 'What is left'} />
      <RowGroup>
        {board.items.map((item) => (
          <ChecklistRow key={item.key} item={item} onAction={handleAction(router, item)} />
        ))}
      </RowGroup>

      {approvedWithoutCheck ? (
        <Text variant="caption" tone="muted" style={styles.reference}>
          The identity rows are not ticked because those checks did not exist when
          your account was approved. Nothing is outstanding and there is nothing for
          you to do.
        </Text>
      ) : null}

      {latest ? <CheckBreakdown attempt={latest} /> : null}

      {stage === 'REJECTED' && latest?.review_note ? (
        <Card style={[styles.notice, { borderColor: palette.danger }]}>
          <Text variant="title3">Why it was not approved</Text>
          <Text variant="body" style={styles.noticeBody}>
            {latest.review_note}
          </Text>
        </Card>
      ) : null}

      {stage === 'RETRY' && latest?.rejection_code ? (
        <Card style={[styles.notice, { borderColor: palette.warning }]}>
          <Text variant="title3">What happened</Text>
          <Text variant="body" style={styles.noticeBody}>
            {rejectionMessage(latest.rejection_code)}
          </Text>
        </Card>
      ) : null}

      {/* The action, whatever it is at this point. */}
      {stage === 'CONTACTS' ? (
        <View style={styles.action}>
          <Button
            label="Verify phone and email"
            onPress={() => router.push('/verify-phone')}
            fullWidth
          />
        </View>
      ) : null}

      {stage === 'READY' || stage === 'RETRY' ? (
        <StartVerification
          reference={reference}
          onChange={setReference}
          onSubmit={onStart}
          busy={busy}
          error={start.error}
          canStart={board.can_start_identity_check}
        />
      ) : null}

      {stage === 'REJECTED' ? (
        <View style={styles.action}>
          <Button
            label="Submit again"
            onPress={() => resubmit.mutate()}
            loading={resubmit.isPending}
            fullWidth
          />
        </View>
      ) : null}

      {resubmit.error ? <InlineError error={resubmit.error} /> : null}

      {history.data && history.data.length > 1 ? (
        <>
          <SectionHeader title="Earlier submissions" />
          <RowGroup>
            {history.data.slice(1).map((row) => (
              <ListRow
                key={row.id}
                title={attemptStatusView(row.status).label}
                subtitle={row.review_note || rejectionMessage(row.rejection_code) || undefined}
                meta={new Date(row.created_at).toLocaleDateString()}
              />
            ))}
          </RowGroup>
        </>
      ) : null}

      <Text variant="caption" tone="muted" style={styles.privacy}>
        Sync never stores your NIN, your photograph or anything the identity service
        sends back beyond the result. What we keep is whether each check passed, the
        reference, and the last four digits so support can identify the right record.
      </Text>
    </Screen>
  );
}

/** Where a checklist item's action button goes, when it has one. */
function handleAction(
  router: ReturnType<typeof useRouter>,
  item: ChecklistItem,
): (() => void) | undefined {
  if (item.action === 'VERIFY_PHONE' || item.action === 'VERIFY_EMAIL') {
    return () => router.push('/verify-phone');
  }
  return undefined;
}

function ChecklistRow({ item, onAction }: { item: ChecklistItem; onAction?: () => void }) {
  const palette = usePalette();

  return (
    <ListRow
      title={item.label}
      icon={item.complete ? 'check' : 'clock'}
      iconTone={item.complete ? 'success' : 'neutral'}
      onPress={onAction}
      chevron={Boolean(onAction)}
      trailing={
        item.complete ? (
          <Icon name="check" size={18} color={palette.success} strokeWidth={2.4} />
        ) : undefined
      }
    />
  );
}

/**
 * The three outcomes, shown separately.
 *
 * They fail independently and for different reasons, and collapsing them into
 * one line would take away the only information that tells a provider what to
 * fix.
 */
function CheckBreakdown({ attempt }: { attempt: ProviderVerification }) {
  const rows = [
    { label: 'NIN identity', status: attempt.identity_check_status },
    { label: 'Face match', status: attempt.face_match_status },
    { label: 'Liveness', status: attempt.liveness_status },
  ];

  return (
    <>
      <SectionHeader title="Checks" />
      <RowGroup>
        {rows.map((row) => {
          const view = checkStatusView(row.status);
          return (
            <ListRow
              key={row.label}
              title={row.label}
              trailing={<Pill label={view.label} tone={view.tone} />}
            />
          );
        })}
      </RowGroup>
      {attempt.masked_identifier ? (
        <Text variant="caption" tone="muted" style={styles.reference}>
          Ends {attempt.masked_identifier}
          {attempt.identity_reference ? ` · ${attempt.identity_reference}` : ''}
        </Text>
      ) : null}
    </>
  );
}

/**
 * Starting a check.
 *
 * The field takes the reference the identity provider hands back after the
 * holder consents there. It is deliberately **not** a NIN field: the server
 * rejects anything carrying eleven consecutive digits before an adapter sees it,
 * and the local fake refuses one outright, so a development database cannot
 * quietly accumulate real identifiers from somebody testing the form.
 */
function StartVerification({
  reference,
  onChange,
  onSubmit,
  busy,
  error,
  canStart,
}: {
  reference: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  busy: boolean;
  error: unknown;
  canStart: boolean;
}) {
  return (
    <Card style={styles.start}>
      <Text variant="title3">Approval reference</Text>
      <Text variant="caption" tone="muted" style={styles.startHint}>
        Approve the check at NIMC, then paste the reference it gives you. Never type
        your NIN here: it is not needed and will be refused.
      </Text>

      <Field
        label="Reference"
        value={reference}
        onChangeText={onChange}
        placeholder="Paste the reference"
        autoCapitalize="none"
        autoCorrect={false}
        hint="Not your NIN. Anything with eleven digits in a row is refused."
      />

      <View style={styles.action}>
        <Button
          label="Start verification"
          onPress={onSubmit}
          loading={busy}
          disabled={!canStart || !reference.trim()}
          fullWidth
        />
      </View>

      <Text variant="caption" tone="muted" style={styles.consent}>
        Starting the check confirms you agree to Sync verifying your identity with
        NIMC through a licensed provider.
      </Text>

      {error ? <InlineError error={error} /> : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  intro: { gap: spacing.xs },
  introBody: { marginTop: spacing.xxs },
  introPill: { alignSelf: 'flex-start', marginTop: spacing.sm },
  notice: { borderWidth: 1, borderRadius: radii.card, marginTop: spacing.md, gap: spacing.xxs },
  noticeBody: { marginTop: spacing.xxs },
  action: { marginTop: spacing.md },
  start: { marginTop: spacing.md, gap: spacing.xs },
  startHint: { marginBottom: spacing.xs },
  consent: { marginTop: spacing.sm },
  reference: { marginTop: spacing.xs },
  privacy: { marginTop: spacing.xl, marginBottom: spacing.xl },
});
