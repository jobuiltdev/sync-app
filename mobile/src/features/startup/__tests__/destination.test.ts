import { isStartupReady, resolveDestination } from '@/features/startup/destination';

describe('resolving the launch destination', () => {
  it('sends an authenticated person home', () => {
    expect(resolveDestination('authenticated', false)).toBe('/home');
    expect(resolveDestination('authenticated', true)).toBe('/home');
  });

  it('does not consult the onboarding flag for a signed-in person', () => {
    // Somebody signed in has self-evidently been through the introduction, and
    // showing it to them because a keychain read came back empty would be
    // absurd. Authentication is checked first for exactly this reason.
    expect(resolveDestination('authenticated', false)).toBe('/home');
  });

  it('introduces a first-time visitor', () => {
    expect(resolveDestination('anonymous', false)).toBe('/onboarding');
  });

  it('sends a returning signed-out person to welcome', () => {
    expect(resolveDestination('anonymous', true)).toBe('/welcome');
  });

  it('never resolves to a fourth place', () => {
    const seen = new Set(
      (['authenticated', 'anonymous', 'loading'] as const).flatMap((status) =>
        [true, false].map((onboarded) => resolveDestination(status, onboarded)),
      ),
    );

    expect([...seen].sort()).toEqual(['/home', '/onboarding', '/welcome']);
  });
});

describe('startup readiness', () => {
  const ready = {
    sessionStatus: 'anonymous' as const,
    onboardingHydrated: true,
    themeHydrated: true,
  };

  it('is ready once all three local reads are in', () => {
    expect(isStartupReady(ready)).toBe(true);
  });

  it('waits for the session', () => {
    expect(isStartupReady({ ...ready, sessionStatus: 'loading' })).toBe(false);
  });

  it('waits for the onboarding flag', () => {
    expect(isStartupReady({ ...ready, onboardingHydrated: false })).toBe(false);
  });

  it('waits for the theme', () => {
    // The theme decides the colour of the first frame. Painting before it is
    // known is what produced the palette flip this coordinator exists to stop.
    expect(isStartupReady({ ...ready, themeHydrated: false })).toBe(false);
  });

  it('treats an authenticated session as resolved', () => {
    expect(isStartupReady({ ...ready, sessionStatus: 'authenticated' })).toBe(true);
  });
});
