import type { DetailsSchema } from '@/api/endpoints/catalog';
import {
  buildSpecSchema,
  initialSpecValues,
  toRequestDetails,
} from '@/features/bookings/spec-form';

const CLEANING: DetailsSchema = {
  key: 'cleaning',
  fields: [
    {
      name: 'property_type',
      type: 'choice',
      required: true,
      label: 'Property type',
      choices: ['APARTMENT', 'HOUSE', 'OFFICE'],
    },
    { name: 'bedrooms', type: 'integer', required: true, label: 'Bedrooms', choices: null },
    { name: 'depth', type: 'choice', required: true, label: 'Depth', choices: ['STANDARD', 'DEEP'] },
    {
      name: 'has_supplies',
      type: 'boolean',
      required: false,
      label: 'Customer provides supplies',
      choices: null,
    },
    { name: 'note', type: 'char', required: false, label: 'Note', choices: null },
  ],
};

const ERRANDS: DetailsSchema = {
  key: 'errands',
  fields: [{ name: 'tasks', type: 'list', required: true, label: 'Tasks', choices: null }],
};

const VALID = {
  property_type: 'APARTMENT',
  bedrooms: '3',
  depth: 'STANDARD',
  has_supplies: false,
  note: '',
};

describe('buildSpecSchema', () => {
  it('accepts a complete payload', () => {
    expect(buildSpecSchema(CLEANING).safeParse(VALID).success).toBe(true);
  });

  it('requires a required choice to be answered', () => {
    const result = buildSpecSchema(CLEANING).safeParse({ ...VALID, depth: '' });

    expect(result.success).toBe(false);
  });

  it('rejects a choice outside the options the service offers', () => {
    const result = buildSpecSchema(CLEANING).safeParse({ ...VALID, property_type: 'CASTLE' });

    expect(result.success).toBe(false);
  });

  it('coerces a numeric field typed into a text input', () => {
    const result = buildSpecSchema(CLEANING).safeParse(VALID);

    expect(result.success && result.data).toMatchObject({ bedrooms: 3 });
  });

  it('rejects a numeric field that is not a number', () => {
    const result = buildSpecSchema(CLEANING).safeParse({ ...VALID, bedrooms: 'three' });

    expect(result.success).toBe(false);
  });

  it('requires a required text field to be non-blank', () => {
    const schema = buildSpecSchema({
      key: 'x',
      fields: [{ name: 'why', type: 'char', required: true, label: 'Why', choices: null }],
    });

    expect(schema.safeParse({ why: '   ' }).success).toBe(false);
    expect(schema.safeParse({ why: 'Leaking pipe' }).success).toBe(true);
  });

  it('requires a required list to have at least one entry', () => {
    expect(buildSpecSchema(ERRANDS).safeParse({ tasks: [] }).success).toBe(false);
    expect(buildSpecSchema(ERRANDS).safeParse({ tasks: ['Buy bread'] }).success).toBe(true);
  });

  it('builds a different form for a different service', () => {
    // The whole point: nothing here knows what cleaning or errands are.
    expect(buildSpecSchema(ERRANDS).safeParse(VALID).success).toBe(false);
  });

  it('tolerates a missing schema rather than crashing the screen', () => {
    expect(buildSpecSchema(undefined).safeParse({}).success).toBe(true);
  });
});

describe('initialSpecValues', () => {
  it('starts a choice unanswered rather than guessing the first option', () => {
    expect(initialSpecValues(CLEANING).property_type).toBe('');
  });

  it('starts a boolean false and a list empty', () => {
    const values = initialSpecValues(CLEANING);

    expect(values.has_supplies).toBe(false);
    expect(initialSpecValues(ERRANDS).tasks).toEqual([]);
  });

  it('covers every field the service declares', () => {
    expect(Object.keys(initialSpecValues(CLEANING))).toHaveLength(CLEANING.fields.length);
  });
});

describe('toRequestDetails', () => {
  it('converts numeric strings to numbers', () => {
    expect(toRequestDetails(CLEANING, VALID)).toMatchObject({ bedrooms: 3 });
  });

  it('omits an optional field the user left blank', () => {
    // Sending "" for an optional field would be rejected by the API for a reason
    // the customer never caused.
    expect(toRequestDetails(CLEANING, VALID)).not.toHaveProperty('note');
  });

  it('keeps a false boolean, which is an answer', () => {
    expect(toRequestDetails(CLEANING, VALID)).toMatchObject({ has_supplies: false });
  });

  it('omits an empty optional list', () => {
    const schema: DetailsSchema = {
      key: 'x',
      fields: [{ name: 'extras', type: 'list', required: false, label: 'Extras', choices: null }],
    };

    expect(toRequestDetails(schema, { extras: [] })).toEqual({});
  });

  it('keeps a required field even when blank, so the API reports it', () => {
    const details = toRequestDetails(CLEANING, { ...VALID, depth: '' });

    expect(details).toHaveProperty('depth');
  });
});
