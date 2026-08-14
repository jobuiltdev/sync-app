import {
  type Payout,
  isPayoutSettling,
  payoutStageMessage,
  payoutStatusLabel,
} from '@/api/endpoints/payments';

function payout(overrides: Partial<Payout> = {}): Payout {
  return {
    id: 'p1',
    amount_kobo: 600_000,
    currency: 'NGN',
    status: 'REQUESTED',
    requested_at: '2026-08-14T10:00:00Z',
    processed_at: null,
    failure_reason: '',
    transfer_reference: '',
    submitted_at: null,
    is_cancellable: true,
    allowed_transitions: [],
    created_at: '2026-08-14T10:00:00Z',
    updated_at: '2026-08-14T10:00:00Z',
    ...overrides,
  };
}

describe('payoutStageMessage', () => {
  it('tells a provider a requested payout can still be called off', () => {
    expect(payoutStageMessage(payout())).toContain('cancel');
  });

  it('says a submitted transfer is being confirmed rather than merely processing', () => {
    // The status alone undersells it: the money has left, or may have, and the
    // honest thing to say is that we are finding out.
    const message = payoutStageMessage(
      payout({ status: 'PROCESSING', transfer_reference: 'SYT-ABC', submitted_at: 'x' }),
    );

    expect(message).toContain('Sent to your bank');
    expect(message).toContain('confirming');
  });

  it('distinguishes a payout still being prepared from one already sent', () => {
    const preparing = payoutStageMessage(payout({ status: 'PROCESSING' }));
    const sent = payoutStageMessage(
      payout({ status: 'PROCESSING', transfer_reference: 'SYT-ABC' }),
    );

    expect(preparing).not.toEqual(sent);
    expect(preparing).toContain('prepared');
  });

  it('says the money came back when a transfer failed', () => {
    const message = payoutStageMessage(
      payout({ status: 'FAILED', failure_reason: 'Account closed.' }),
    );

    expect(message).toContain('Account closed.');
    expect(message).toContain('back in your balance');
  });

  it('says the money came back on a failure with no stated reason', () => {
    expect(payoutStageMessage(payout({ status: 'FAILED' }))).toContain('back in your balance');
  });

  it('says the money came back when the provider cancelled it', () => {
    expect(payoutStageMessage(payout({ status: 'CANCELLED' }))).toContain('back in your balance');
  });

  it('confirms a paid payout plainly', () => {
    expect(payoutStageMessage(payout({ status: 'PAID' }))).toContain('Sent to your bank account');
  });

  it('never tells a provider a payout is paid while it is still being confirmed', () => {
    const message = payoutStageMessage(
      payout({ status: 'PROCESSING', transfer_reference: 'SYT-ABC' }),
    );

    expect(message).not.toMatch(/^Paid/);
  });
});

describe('isPayoutSettling', () => {
  it('keeps watching while a payout is still moving', () => {
    expect(isPayoutSettling(payout({ status: 'REQUESTED' }))).toBe(true);
    expect(isPayoutSettling(payout({ status: 'PROCESSING' }))).toBe(true);
  });

  it('stops once the payout is finished', () => {
    // A background task resolves a submitted transfer within minutes, so polling
    // past a terminal state is asking a question that already has its answer.
    expect(isPayoutSettling(payout({ status: 'PAID' }))).toBe(false);
    expect(isPayoutSettling(payout({ status: 'FAILED' }))).toBe(false);
    expect(isPayoutSettling(payout({ status: 'CANCELLED' }))).toBe(false);
  });

  it('does not poll when there is nothing loaded yet', () => {
    expect(isPayoutSettling(undefined)).toBe(false);
  });
});

describe('payoutStatusLabel', () => {
  it('says where the money is, in the provider terms', () => {
    expect(payoutStatusLabel('PROCESSING')).toBe('On its way to your bank');
    expect(payoutStatusLabel('PAID')).toBe('Paid');
  });
});
