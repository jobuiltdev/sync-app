import { toKobo, validateAmount } from '@/features/payments/amount';
import { newIdempotencyKey } from '@/lib/idempotency';

const AVAILABLE = 1_600_000;

describe('toKobo', () => {
  it('converts whole naira to kobo', () => {
    expect(toKobo('16000')).toBe(1_600_000);
    expect(toKobo('1')).toBe(100);
  });

  it('tolerates surrounding whitespace', () => {
    expect(toKobo('  500 ')).toBe(50_000);
  });

  it('refuses anything that is not a whole number', () => {
    for (const input of ['', '  ', 'abc', '1.5', '-100', '1e3', '1,000', '₦500']) {
      expect(toKobo(input)).toBeNull();
    }
  });

  it('returns an integer, never a float', () => {
    const kobo = toKobo('12345');

    expect(Number.isInteger(kobo)).toBe(true);
  });
});

describe('validateAmount', () => {
  it('accepts an amount within the balance', () => {
    expect(validateAmount('10000', AVAILABLE)).toEqual({ kobo: 1_000_000, error: null });
  });

  it('accepts the entire balance', () => {
    expect(validateAmount('16000', AVAILABLE).error).toBeNull();
  });

  it('asks for an amount when the field is empty', () => {
    expect(validateAmount('', AVAILABLE).error).toBe('Enter an amount.');
  });

  it('refuses zero', () => {
    expect(validateAmount('0', AVAILABLE).error).toBe('Enter an amount greater than zero.');
  });

  it('refuses a negative amount', () => {
    // It never parses as a number of naira in the first place, so the message is
    // about the format rather than about the sign.
    expect(validateAmount('-500', AVAILABLE).error).toBe('Enter a whole number of naira.');
  });

  it('refuses more than the balance and says what the balance is', () => {
    const { error } = validateAmount('20000', AVAILABLE);

    expect(error).toContain('more than your');
    expect(error).toContain('16,000');
  });

  it('refuses everything when the balance is zero', () => {
    expect(validateAmount('1', 0).error).toContain('more than your');
  });

  it('refuses a fractional amount rather than rounding it', () => {
    expect(validateAmount('100.50', AVAILABLE).error).toBe('Enter a whole number of naira.');
  });
});

describe('newIdempotencyKey', () => {
  it('produces a different key each time', () => {
    const keys = new Set(Array.from({ length: 200 }, newIdempotencyKey));

    expect(keys.size).toBe(200);
  });

  it('produces something short enough for the header the API accepts', () => {
    expect(newIdempotencyKey().length).toBeLessThanOrEqual(100);
  });

  it('produces a key with no characters that would need escaping in a header', () => {
    expect(newIdempotencyKey()).toMatch(/^[a-z0-9-]+$/);
  });
});
