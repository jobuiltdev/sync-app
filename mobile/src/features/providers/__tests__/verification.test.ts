/**
 * Provider identity verification, on the client.
 *
 * The client's job here is to render what the server decided and to send almost
 * nothing back. So these tests are mostly about what the app must *not* do:
 * compute its own eligibility, invent an approval, or carry an identifier
 * anywhere near a request.
 */

import type {
  ProviderVerification,
  VerificationChecklist,
} from '@/api/endpoints/providers';
import { startVerification } from '@/api/endpoints/providers';
import {
  STAGE_COPY,
  attemptStatusView,
  checkStatusView,
  rejectionMessage,
  verificationStage,
} from '@/features/providers/verification-presentation';

function checklist(overrides: Partial<VerificationChecklist> = {}): VerificationChecklist {
  return {
    items: [
      { key: 'phone', label: 'Phone number confirmed', complete: true, action: '' },
      { key: 'email', label: 'Email address confirmed', complete: true, action: '' },
      { key: 'identity', label: 'Identity confirmed with NIMC', complete: false, action: 'START_IDENTITY' },
      { key: 'biometrics', label: 'Face match and liveness', complete: false, action: 'START_IDENTITY' },
      { key: 'review', label: 'Reviewed by the Sync team', complete: false, action: '' },
    ],
    complete: false,
    can_start_identity_check: true,
    blocked_reason: '',
    verification_status: 'PENDING',
    ...overrides,
  };
}

function attempt(overrides: Partial<ProviderVerification> = {}): ProviderVerification {
  return {
    id: 'a1',
    status: 'DRAFT',
    submitted_at: null,
    identity_check_status: 'PENDING',
    face_match_status: 'PENDING',
    liveness_status: 'PENDING',
    identity_vendor: '',
    identity_reference: '',
    identity_method: '',
    identity_checked_at: null,
    masked_identifier: '',
    rejection_code: '',
    consent_notice_version: '2026-08-v1',
    consented_at: null,
    review_note: '',
    reviewed: false,
    reviewed_at: null,
    failed_checks: [],
    created_at: '2026-08-26T10:00:00Z',
    ...overrides,
  };
}

describe('which stage the provider is looking at', () => {
  it('asks for contacts first', () => {
    const stage = verificationStage(
      checklist({ blocked_reason: 'CONTACT_NOT_VERIFIED', can_start_identity_check: false }),
      undefined,
    );

    expect(stage).toBe('CONTACTS');
  });

  it('is ready once contacts are done and nothing has been started', () => {
    expect(verificationStage(checklist(), undefined)).toBe('READY');
  });

  it('shows a retry after a failed check', () => {
    const stage = verificationStage(
      checklist(),
      attempt({ status: 'CHECK_FAILED', face_match_status: 'FAILED' }),
    );

    expect(stage).toBe('RETRY');
  });

  it('shows the wait once checks have passed', () => {
    const stage = verificationStage(
      checklist({ verification_status: 'UNDER_REVIEW', blocked_reason: 'AWAITING_REVIEW' }),
      attempt({ status: 'UNDER_REVIEW' }),
    );

    expect(stage).toBe('AWAITING_REVIEW');
  });

  it('shows a rejection with its reason', () => {
    const stage = verificationStage(checklist(), attempt({ status: 'REJECTED' }));

    expect(stage).toBe('REJECTED');
  });

  it('reports approval only from the profile status', () => {
    // An attempt saying APPROVED is not what makes a provider approved: the
    // profile lifecycle is. If the client read the attempt instead, a bug on
    // either side would show somebody as verified when they are not.
    const stage = verificationStage(
      checklist({ verification_status: 'APPROVED' }),
      attempt({ status: 'APPROVED' }),
    );

    expect(stage).toBe('APPROVED');
  });

  it('never reports approval from a passed check alone', () => {
    const stage = verificationStage(
      checklist({ verification_status: 'UNDER_REVIEW' }),
      attempt({
        status: 'UNDER_REVIEW',
        identity_check_status: 'PASSED',
        face_match_status: 'PASSED',
        liveness_status: 'PASSED',
      }),
    );

    expect(stage).not.toBe('APPROVED');
  });

  it('shows suspension over anything else', () => {
    const stage = verificationStage(
      checklist({ verification_status: 'SUSPENDED' }),
      attempt({ status: 'APPROVED' }),
    );

    expect(stage).toBe('SUSPENDED');
  });

  it('falls back to contacts when the server has not answered yet', () => {
    expect(verificationStage(undefined, undefined)).toBe('CONTACTS');
  });

  it('has copy for every stage', () => {
    for (const stage of [
      'CONTACTS',
      'READY',
      'CHECKING',
      'RETRY',
      'AWAITING_REVIEW',
      'REJECTED',
      'APPROVED',
      'APPROVED_WITHOUT_CHECK',
      'SUSPENDED',
    ] as const) {
      expect(STAGE_COPY[stage].title).toBeTruthy();
      expect(STAGE_COPY[stage].body).toBeTruthy();
    }
  });
});

describe('the client decides nothing', () => {
  it('does not work out eligibility from the individual items', () => {
    // The server says no; every item that matters says yes. The client must
    // still say no, because the server knows about things the items do not.
    const board = checklist({
      can_start_identity_check: false,
      blocked_reason: 'AWAITING_REVIEW',
    });

    expect(board.can_start_identity_check).toBe(false);
    expect(verificationStage(board, attempt({ status: 'UNDER_REVIEW' }))).toBe(
      'AWAITING_REVIEW',
    );
  });

  it('renders the server labels rather than inventing its own', () => {
    const board = checklist();

    expect(board.items.map((item) => item.label)).toEqual([
      'Phone number confirmed',
      'Email address confirmed',
      'Identity confirmed with NIMC',
      'Face match and liveness',
      'Reviewed by the Sync team',
    ]);
  });
});

describe('how the three checks read', () => {
  it('names each outcome', () => {
    expect(checkStatusView('PASSED').label).toBe('Passed');
    expect(checkStatusView('FAILED').label).toBe('Failed');
    expect(checkStatusView('PENDING').label).toBe('Not checked yet');
    expect(checkStatusView('UNAVAILABLE').label).toBe('Could not be checked');
  });

  it('colours a failure as a failure', () => {
    expect(checkStatusView('FAILED').tone).toBe('danger');
    expect(checkStatusView('PASSED').tone).toBe('success');
  });

  it('marks the states that are still moving', () => {
    expect(attemptStatusView('CHECKING').live).toBe(true);
    expect(attemptStatusView('UNDER_REVIEW').live).toBe(true);
    expect(attemptStatusView('REJECTED').live).toBe(false);
  });

  it('says a failed check has not been sent for review', () => {
    // The distinction a provider most needs: nothing has gone to a person yet.
    expect(attemptStatusView('CHECK_FAILED').detail).toMatch(/been sent for review/i);
  });
});

describe('rejection messages', () => {
  it('gives an actionable line for every known code', () => {
    for (const code of [
      'IDENTITY_NOT_FOUND',
      'IDENTITY_MISMATCH',
      'FACE_MISMATCH',
      'LIVENESS_FAILED',
      'CONSENT_DECLINED',
      'AUTHORIZATION_EXPIRED',
      'IDENTITY_ALREADY_USED',
      'VENDOR_UNAVAILABLE',
    ]) {
      expect(rejectionMessage(code).length).toBeGreaterThan(20);
    }
  });

  it('says nothing when there is nothing to say', () => {
    expect(rejectionMessage('')).toBe('');
  });

  it('falls back rather than showing a raw code', () => {
    // A vendor's own vocabulary must never reach a provider's screen.
    const message = rejectionMessage('SOME_NEW_VENDOR_CODE');

    expect(message).not.toContain('SOME_NEW_VENDOR_CODE');
    expect(message.length).toBeGreaterThan(10);
  });

  it('never quotes a vendor or an identifier', () => {
    for (const code of ['IDENTITY_NOT_FOUND', 'FACE_MISMATCH', 'LIVENESS_FAILED']) {
      const message = rejectionMessage(code).toLowerCase();
      expect(message).not.toContain('nin:');
      expect(message).not.toContain('bvn');
      expect(message).not.toMatch(/\d{11}/);
    }
  });
});

describe('what the client is even able to send', () => {
  it('sends a reference and a consent flag, and nothing else', () => {
    // The signature is the control here: there is no parameter for a status, an
    // outcome, a review field or an identifier.
    expect(startVerification).toHaveLength(1);
  });

  it('carries no identifier field anywhere in the attempt shape', () => {
    const shape = Object.keys(attempt());

    for (const forbidden of ['nin', 'bvn', 'selfie', 'portrait', 'token', 'payload', 'image']) {
      expect(shape.join(' ').toLowerCase()).not.toContain(forbidden);
    }
  });

  it('keeps the masked identifier to four characters', () => {
    const withMask = attempt({ masked_identifier: '4821' });

    expect(withMask.masked_identifier.length).toBeLessThanOrEqual(4);
  });
});

/**
 * Approved with no attempt behind it.
 *
 * Accounts approved before Phase V1 existed, and accounts approved by hand in a
 * test database, carry `verification_status: APPROVED` with no attempt row at
 * all. The screen must say what is true of them without inventing a NIN, face or
 * liveness result that never ran, and without falling back to an error.
 */
describe('an approved provider with no verification history', () => {
  const approvedBoard = checklist({
    verification_status: 'APPROVED',
    blocked_reason: 'ALREADY_APPROVED',
    can_start_identity_check: false,
    items: [
      { key: 'phone', label: 'Phone number confirmed', complete: true, action: '' },
      { key: 'email', label: 'Email address confirmed', complete: true, action: '' },
      { key: 'identity', label: 'Identity confirmed with NIMC', complete: false, action: '' },
      { key: 'biometrics', label: 'Face match and liveness', complete: false, action: '' },
      { key: 'review', label: 'Reviewed by the Sync team', complete: true, action: '' },
    ],
  });

  it('is its own stage, not the ordinary approved one', () => {
    expect(verificationStage(approvedBoard, null)).toBe('APPROVED_WITHOUT_CHECK');
  });

  it('does not claim any identity check ran', () => {
    const copy = STAGE_COPY[verificationStage(approvedBoard, null)];
    const words = `${copy.title} ${copy.body}`.toLowerCase();

    expect(words).toContain('no nin, face match or liveness check is on file');
    expect(words).not.toContain('your checks passed');
    expect(words).not.toContain('you are verified');
  });

  it('still tells them they can work', () => {
    const copy = STAGE_COPY[verificationStage(approvedBoard, null)];

    expect(`${copy.title} ${copy.body}`.toLowerCase()).toContain('take work');
  });

  it('leaves the two identity rows untouched rather than ticking them', () => {
    // The server sends them incomplete because they are. Nothing on the client
    // may flip them: a fabricated tick here is a claim that a paid check ran.
    const identity = approvedBoard.items.find((item) => item.key === 'identity');
    const biometrics = approvedBoard.items.find((item) => item.key === 'biometrics');

    expect(identity?.complete).toBe(false);
    expect(biometrics?.complete).toBe(false);
    expect(verificationStage(approvedBoard, null)).toBe('APPROVED_WITHOUT_CHECK');
  });

  it('offers no way to start a check, since approval is already settled', () => {
    expect(approvedBoard.can_start_identity_check).toBe(false);
  });

  it('reads as ordinary approval once an attempt does exist', () => {
    expect(verificationStage(approvedBoard, attempt({ status: 'APPROVED' }))).toBe('APPROVED');
  });

  it('does not show the legacy state while the attempt query is still out', () => {
    // undefined is "not answered yet", null is "answered, there is none". A
    // loading screen must not announce that somebody has no checks on file.
    expect(verificationStage(approvedBoard, undefined)).toBe('APPROVED');
  });

  it('has copy for the stage', () => {
    expect(STAGE_COPY.APPROVED_WITHOUT_CHECK.title).toBeTruthy();
    expect(STAGE_COPY.APPROVED_WITHOUT_CHECK.body).toBeTruthy();
  });
});

describe('a suspended provider with no attempt', () => {
  it('is still suspension, which outranks everything', () => {
    const board = checklist({ verification_status: 'SUSPENDED', blocked_reason: 'SUSPENDED' });

    expect(verificationStage(board, null)).toBe('SUSPENDED');
  });
});

describe('an unapproved provider with no attempt', () => {
  it('is ready to start, not a legacy approval', () => {
    expect(verificationStage(checklist(), null)).toBe('READY');
  });
});
