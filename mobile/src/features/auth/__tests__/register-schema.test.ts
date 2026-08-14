import { registerSchema } from '@/features/auth/register-schema';

const VALID = {
  first_name: 'Ada',
  last_name: 'Okeke',
  email: 'ada@example.com',
  phone: '0803 123 4567',
  password: 'Lagos-Rider-2026',
};

function errorFor(field: string, values: Record<string, unknown>): string | undefined {
  const result = registerSchema.safeParse(values);
  if (result.success) return undefined;

  return result.error.issues.find((issue) => issue.path[0] === field)?.message;
}

describe('registerSchema', () => {
  it('accepts a complete form', () => {
    expect(registerSchema.safeParse(VALID).success).toBe(true);
  });

  it('will not submit without a phone number', () => {
    expect(errorFor('phone', { ...VALID, phone: '' })).toBe('Enter your phone number.');
  });

  it('will not submit with a phone number that is only whitespace', () => {
    expect(errorFor('phone', { ...VALID, phone: '   ' })).toBe('Enter your phone number.');
  });

  it('will not submit when the phone field is missing altogether', () => {
    const { phone, ...withoutPhone } = VALID;

    expect(registerSchema.safeParse(withoutPhone).success).toBe(false);
    expect(phone).toBeDefined();
  });

  it('rejects a number too short to be a real one', () => {
    expect(errorFor('phone', { ...VALID, phone: '0803 123' })).toBe('Enter a full phone number.');
  });

  it('accepts the ways a Nigerian number is actually typed', () => {
    for (const phone of [
      '08031234567',
      '0803 123 4567',
      '0803-123-4567',
      '+2348031234567',
      '+234 803 123 4567',
    ]) {
      expect(registerSchema.safeParse({ ...VALID, phone }).success).toBe(true);
    }
  });

  it('leaves normalisation to the server rather than reformatting the number', () => {
    // The value that reaches the API is what the person typed, trimmed. Turning
    // it into E.164 here would be a second implementation of a rule the server
    // already owns, and the two would eventually disagree.
    const parsed = registerSchema.parse({ ...VALID, phone: '  0803 123 4567  ' });

    expect(parsed.phone).toBe('0803 123 4567');
  });

  it('still requires everything it required before', () => {
    expect(errorFor('first_name', { ...VALID, first_name: '' })).toBe('Enter your first name.');
    expect(errorFor('last_name', { ...VALID, last_name: '' })).toBe('Enter your last name.');
    expect(errorFor('email', { ...VALID, email: 'not-an-email' })).toBe(
      'Enter a valid email address.',
    );
    expect(errorFor('password', { ...VALID, password: '' })).toBe('Choose a password.');
  });

  it('reports every missing field at once rather than one at a time', () => {
    const result = registerSchema.safeParse({
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      password: '',
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(new Set(result.error.issues.map((issue) => issue.path[0]))).toEqual(
        new Set(['first_name', 'last_name', 'email', 'phone', 'password']),
      );
    }
  });
});
