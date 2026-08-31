import { resetAuthPlumbing, setAccessTokenProvider } from '@/api/client';
import {
  type ProviderProfile,
  type ProviderService,
  type ProviderServiceArea,
  type ProviderVerification,
  type VerificationChecklist,
  addProviderArea,
  addProviderService,
  createProviderProfile,
  eligibilityGaps,
  fetchProviderProfile,
  fetchVerification,
  fetchVerificationChecklist,
  fetchVerificationHistory,
  removeProviderService,
  resubmitVerification,
  startVerification,
  updateProviderProfile,
  verificationStatusLabel,
} from '@/api/endpoints/providers';

const BASE_URL = 'http://192.168.1.24:8000';

function jsonResponse(status: number, body: unknown): Response {
  // 204 means no content, and the Response constructor refuses a body with one.
  if (status === 204) return new Response(null, { status });

  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function mockFetch(response: Response): jest.Mock {
  const fetchMock = jest.fn().mockResolvedValue(response);
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

const PROFILE: ProviderProfile = {
  id: 'p1',
  display_name: 'Ada Cleaning',
  bio: '',
  provider_type: 'INDIVIDUAL',
  business_name: '',
  verification_status: 'APPROVED',
  is_accepting_jobs: true,
  created_at: '2026-08-14T10:00:00Z',
  updated_at: '2026-08-14T10:00:00Z',
};

const SERVICE: ProviderService = {
  id: 's1',
  service_slug: 'standard-clean',
  service_name: 'Standard Clean',
  price_override_kobo: null,
  effective_price_kobo: 2_000_000,
  experience_years: null,
  is_active: true,
};

const AREA: ProviderServiceArea = { id: 'a1', state: 'LAGOS', lga: '' };

const CHECKLIST: VerificationChecklist = {
  items: [
    { key: 'phone', label: 'Phone number confirmed', complete: true, action: '' },
    { key: 'email', label: 'Email address confirmed', complete: true, action: '' },
    {
      key: 'identity',
      label: 'Identity confirmed with NIMC',
      complete: false,
      action: 'START_IDENTITY',
    },
    {
      key: 'biometrics',
      label: 'Face match and liveness',
      complete: false,
      action: 'START_IDENTITY',
    },
    { key: 'review', label: 'Reviewed by the Sync team', complete: false, action: '' },
  ],
  complete: false,
  can_start_identity_check: true,
  blocked_reason: '',
  verification_status: 'PENDING',
};

const ATTEMPT: ProviderVerification = {
  id: 'v1',
  status: 'UNDER_REVIEW',
  submitted_at: '2026-08-26T10:05:00Z',
  identity_check_status: 'PASSED',
  face_match_status: 'PASSED',
  liveness_status: 'PASSED',
  identity_vendor: 'fake',
  identity_reference: 'FAKE-0123456789ABCDEF',
  identity_method: 'NIN',
  identity_checked_at: '2026-08-26T10:05:00Z',
  masked_identifier: '4821',
  rejection_code: '',
  consent_notice_version: '2026-08-v1',
  consented_at: '2026-08-26T10:04:00Z',
  review_note: '',
  reviewed: false,
  reviewed_at: null,
  failed_checks: [],
  created_at: '2026-08-26T10:04:00Z',
};

describe('provider api', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    process.env.EXPO_PUBLIC_API_URL = BASE_URL;
    resetAuthPlumbing();
    setAccessTokenProvider(() => 'token');
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it('reads the profile', async () => {
    const fetchMock = mockFetch(jsonResponse(200, PROFILE));

    await expect(fetchProviderProfile()).resolves.toMatchObject({ display_name: 'Ada Cleaning' });
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/provider/profile/`);
  });

  it('creates a profile through its own route', async () => {
    const fetchMock = mockFetch(jsonResponse(201, PROFILE));

    await createProviderProfile({ display_name: 'Ada Cleaning' });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/provider/profile/create/`);
    expect(init.method).toBe('POST');
  });

  it('never sends a verification status', async () => {
    // Approval is adjudicated. A client that could send it could approve itself.
    const fetchMock = mockFetch(jsonResponse(201, PROFILE));

    await createProviderProfile({ display_name: 'Ada Cleaning', bio: 'Ten years' });

    expect(fetchMock.mock.calls[0][1].body).not.toContain('verification_status');
    expect(fetchMock.mock.calls[0][1].body).not.toContain('APPROVED');
  });

  it('updates with PATCH so untouched fields are not reset', async () => {
    const fetchMock = mockFetch(jsonResponse(200, PROFILE));

    await updateProviderProfile({ is_accepting_jobs: false });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/provider/profile/`);
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body)).toEqual({ is_accepting_jobs: false });
  });

  it('adds a service by slug', async () => {
    const fetchMock = mockFetch(jsonResponse(201, SERVICE));

    await addProviderService('standard-clean');

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      service_slug: 'standard-clean',
    });
  });

  it('removes a service by id', async () => {
    const fetchMock = mockFetch(jsonResponse(204, null));

    await removeProviderService('s1');

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/provider/services/s1/`);
    expect(init.method).toBe('DELETE');
  });

  it('adds an area, where a blank lga means the whole state', async () => {
    const fetchMock = mockFetch(jsonResponse(201, AREA));

    await addProviderArea('LAGOS');

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ state: 'LAGOS', lga: '' });
  });

  it('surfaces a duplicate service as the server code', async () => {
    mockFetch(
      jsonResponse(400, {
        error: {
          code: 'SERVICE_ALREADY_OFFERED',
          message: 'You already offer this service.',
          details: {},
        },
      }),
    );

    await expect(addProviderService('standard-clean')).rejects.toMatchObject({
      code: 'SERVICE_ALREADY_OFFERED',
    });
  });

  it('surfaces an account with no provider side as a not found', async () => {
    // Not an error: most accounts are customers.
    mockFetch(
      jsonResponse(404, {
        error: {
          code: 'PROVIDER_PROFILE_NOT_FOUND',
          message: 'This account does not have a provider profile yet.',
          details: {},
        },
      }),
    );

    await expect(fetchProviderProfile()).rejects.toMatchObject({
      code: 'PROVIDER_PROFILE_NOT_FOUND',
      status: 404,
    });
  });
});

describe('verificationStatusLabel', () => {
  it('says where a provider stands, in their terms', () => {
    expect(verificationStatusLabel('PENDING')).toBe('Not submitted yet');
    expect(verificationStatusLabel('UNDER_REVIEW')).toBe('Being reviewed');
    expect(verificationStatusLabel('APPROVED')).toBe('Approved');
  });

  it('falls back to the raw code rather than rendering nothing', () => {
    expect(verificationStatusLabel('SOMETHING_NEW' as never)).toBe('SOMETHING_NEW');
  });
});

describe('eligibilityGaps', () => {
  it('is empty when a provider is fully set up', () => {
    expect(eligibilityGaps(PROFILE, [SERVICE], [AREA], true, true)).toEqual([]);
  });

  it('asks for a profile first when there is none', () => {
    const gaps = eligibilityGaps(undefined, undefined, undefined, true, true);

    expect(gaps).toHaveLength(1);
    expect(gaps[0].reason).toContain('provider profile');
  });

  it('explains an unapproved provider without offering a way to self approve', () => {
    const gaps = eligibilityGaps(
      { ...PROFILE, verification_status: 'UNDER_REVIEW' },
      [SERVICE],
      [AREA],
      true,
      true,
    );

    expect(gaps[0].reason).toContain('being reviewed');
    // The route points back at this screen, which has no control that changes it.
    expect(gaps[0].route).toBe('/provider');
  });

  it('notices a provider who has turned work off', () => {
    const gaps = eligibilityGaps(
      { ...PROFILE, is_accepting_jobs: false },
      [SERVICE],
      [AREA],
      true,
      true,
    );

    expect(gaps.some((gap) => gap.reason.includes('not taking work'))).toBe(true);
  });

  it('notices no services and no areas', () => {
    const gaps = eligibilityGaps(PROFILE, [], [], true, true);

    expect(gaps.some((gap) => gap.reason.includes('not listed any services'))).toBe(true);
    expect(gaps.some((gap) => gap.reason.includes('where you work'))).toBe(true);
  });

  it('treats an inactive service as no service', () => {
    const gaps = eligibilityGaps(PROFILE, [{ ...SERVICE, is_active: false }], [AREA], true, true);

    expect(gaps.some((gap) => gap.reason.includes('not listed any services'))).toBe(true);
  });

  it('names the verification an accept will need', () => {
    // ACCEPT_JOB requires both channels, and a provider finds that out at the
    // worst moment unless it is said here first.
    const gaps = eligibilityGaps(PROFILE, [SERVICE], [AREA], true, false);

    expect(gaps).toHaveLength(1);
    expect(gaps[0].reason).toContain('verified phone and email');
    expect(gaps[0].route).toBe('/verify-phone');
  });

  it('reports every gap at once rather than one at a time', () => {
    const gaps = eligibilityGaps(
      { ...PROFILE, verification_status: 'PENDING', is_accepting_jobs: false },
      [],
      [],
      false,
      false,
    );

    expect(gaps).toHaveLength(5);
  });
});

/**
 * Verification routing.
 *
 * These five shipped without the `/api/v1` prefix while every other call in the
 * same module had it, so each one reached Django's 404 handler and the whole
 * feature was dead on a device while every unit test still passed. Nothing here
 * asserted a URL, so nothing caught it.
 *
 * The assertions below are deliberately whole absolute URLs rather than a
 * `toContain('verification')`, because the missing half is exactly the half a
 * substring match would have skipped over.
 */
describe('verification endpoints address the versioned API', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    process.env.EXPO_PUBLIC_API_URL = BASE_URL;
    resetAuthPlumbing();
    setAccessTokenProvider(() => 'token');
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it('reads the checklist from the full path', async () => {
    const fetchMock = mockFetch(jsonResponse(200, CHECKLIST));

    await fetchVerificationChecklist();

    expect(fetchMock.mock.calls[0][0]).toBe(
      `${BASE_URL}/api/v1/provider/verification/checklist/`,
    );
  });

  it('reads the latest attempt from the full path', async () => {
    const fetchMock = mockFetch(jsonResponse(200, ATTEMPT));

    await fetchVerification();

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/provider/verification/`);
  });

  it('reads the history from the full path', async () => {
    const fetchMock = mockFetch(jsonResponse(200, [ATTEMPT]));

    await fetchVerificationHistory();

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/provider/verification/history/`);
  });

  it('starts a check at the full path, with POST', async () => {
    const fetchMock = mockFetch(jsonResponse(201, ATTEMPT));

    await startVerification({ authorization_reference: 'sync-fake-pass', consent: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/provider/verification/start/`);
    expect(init.method).toBe('POST');
  });

  it('resubmits at the full path, with POST', async () => {
    const fetchMock = mockFetch(jsonResponse(201, ATTEMPT));

    await resubmitVerification();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/provider/verification/resubmit/`);
    expect(init.method).toBe('POST');
  });

  it('leaves no verification call on an unversioned path', async () => {
    // The regression itself, stated once over all five rather than five times.
    // A new endpoint added without the prefix fails here even if whoever added
    // it wrote no URL assertion of its own.
    const calls: string[] = [];
    const fetchMock = jest.fn().mockImplementation((url: string) => {
      calls.push(url);
      return Promise.resolve(jsonResponse(200, ATTEMPT));
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await fetchVerificationChecklist();
    await fetchVerification();
    await fetchVerificationHistory();
    await startVerification({ authorization_reference: 'sync-fake-pass', consent: true });
    await resubmitVerification();

    expect(calls).toHaveLength(5);
    for (const url of calls) {
      expect(url.startsWith(`${BASE_URL}/api/v1/provider/verification/`)).toBe(true);
    }
  });
});

describe('a provider who has never started a check', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    process.env.EXPO_PUBLIC_API_URL = BASE_URL;
    resetAuthPlumbing();
    setAccessTokenProvider(() => 'token');
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it('reads as null rather than as a failure', async () => {
    mockFetch(
      jsonResponse(404, {
        error: {
          code: 'NO_VERIFICATION_ATTEMPT',
          message: 'This provider has not started verification.',
          details: {},
        },
      }),
    );

    await expect(fetchVerification()).resolves.toBeNull();
  });

  it('still fails on a 404 that is not that answer', async () => {
    // A bare 404 is what a wrong path produces, and Django answers it with HTML
    // rather than the envelope. Swallowing it would have hidden the routing bug
    // these tests exist for: the screen would have shown an empty first-time
    // state forever and nothing would have looked broken.
    mockFetch(new Response('<h1>Not Found</h1>', { status: 404 }));

    await expect(fetchVerification()).rejects.toMatchObject({
      code: 'UNEXPECTED_RESPONSE',
      status: 404,
    });
  });

  it('still fails on a real server error', async () => {
    mockFetch(
      jsonResponse(500, {
        error: { code: 'INTERNAL', message: 'Something went wrong.', details: {} },
      }),
    );

    await expect(fetchVerification()).rejects.toMatchObject({ code: 'INTERNAL' });
  });
});
