import {
  confirmPhoneVerification,
  requestPhoneVerification,
  updatePhone,
} from '@/api/endpoints/auth';
import { resetAuthPlumbing, setAccessTokenProvider } from '@/api/client';

const BASE_URL = 'http://192.168.1.24:8000';

function jsonResponse(status: number, body: unknown): Response {
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

const CHALLENGE = {
  challenge_id: 'c1f2c3d4-0000-4000-8000-000000000000',
  destination: '+2348031234567',
  expires_at: '2026-08-12T10:10:00Z',
  attempts_remaining: 5,
  resend_available_in_seconds: 60,
};

describe('phone verification api', () => {
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

  it('requests a code from the verification endpoint', async () => {
    const fetchMock = mockFetch(jsonResponse(201, CHALLENGE));

    await expect(requestPhoneVerification()).resolves.toMatchObject({
      challenge_id: CHALLENGE.challenge_id,
    });
    expect(fetchMock.mock.calls[0][0]).toBe(
      `${BASE_URL}/api/v1/auth/phone/verification/request/`,
    );
  });

  it('never receives a code in the challenge response', async () => {
    mockFetch(jsonResponse(201, CHALLENGE));

    const challenge = await requestPhoneVerification();

    expect(challenge).not.toHaveProperty('code');
    expect(JSON.stringify(challenge)).not.toMatch(/\b\d{6}\b/);
  });

  it('submits the challenge id alongside the code', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { is_phone_verified: true }));

    await confirmPhoneVerification(CHALLENGE.challenge_id, '123456');

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ challenge_id: CHALLENGE.challenge_id, code: '123456' });
  });

  it('surfaces a wrong code with its attempts remaining', async () => {
    mockFetch(
      jsonResponse(400, {
        error: {
          code: 'INVALID_PHONE_VERIFICATION_CODE',
          message: 'That code is not correct.',
          details: { attempts_remaining: 4 },
        },
      }),
    );

    await expect(confirmPhoneVerification(CHALLENGE.challenge_id, '000000')).rejects.toMatchObject({
      code: 'INVALID_PHONE_VERIFICATION_CODE',
      details: { attempts_remaining: 4 },
    });
  });

  it('surfaces a cooldown with its retry window', async () => {
    mockFetch(
      jsonResponse(429, {
        error: {
          code: 'PHONE_VERIFICATION_COOLDOWN',
          message: 'Wait a moment.',
          details: { retry_after_seconds: 42 },
        },
      }),
    );

    await expect(requestPhoneVerification()).rejects.toMatchObject({
      code: 'PHONE_VERIFICATION_COOLDOWN',
      status: 429,
    });
  });

  it('surfaces an expired challenge', async () => {
    mockFetch(
      jsonResponse(410, {
        error: { code: 'PHONE_VERIFICATION_EXPIRED', message: 'Expired.' },
      }),
    );

    await expect(confirmPhoneVerification(CHALLENGE.challenge_id, '123456')).rejects.toMatchObject({
      code: 'PHONE_VERIFICATION_EXPIRED',
    });
  });

  it('updates the phone number through its own endpoint', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { phone: '+2348039998877' }));

    await updatePhone('0803 999 8877');

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/auth/phone/`);
    expect(fetchMock.mock.calls[0][1].method).toBe('PUT');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ phone: '0803 999 8877' });
  });

  it('never sends a verified flag anywhere', async () => {
    // Only a correct code sets this, server-side. There is no client path to it.
    const fetchMock = mockFetch(jsonResponse(200, { is_phone_verified: true }));

    await confirmPhoneVerification(CHALLENGE.challenge_id, '123456');
    await updatePhone('08031234567');

    for (const call of fetchMock.mock.calls) {
      expect(call[1].body ?? '').not.toContain('phone_verified');
    }
  });
});
