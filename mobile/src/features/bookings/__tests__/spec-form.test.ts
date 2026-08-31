import type { DetailsField, DetailsSchema } from '@/api/endpoints/catalog';
import { ApiError } from '@/api/errors';
import {
  buildSpecSchema,
  initialSpecValues,
  optionsDeltaKobo,
  toRequestDetails,
  toSpecFieldErrors,
  withDrafts,
} from '@/features/bookings/spec-form';

/**
 * A field as the API sends it.
 *
 * Every presentation key is filled in, because the server always sends them.
 * Making them optional on the type would have let a screen forget to render help
 * text without TypeScript noticing.
 */
function field(overrides: Partial<DetailsField> & Pick<DetailsField, 'name' | 'type'>): DetailsField {
  return {
    required: false,
    label: overrides.name,
    choices: null,
    help_text: '',
    style: '',
    placeholder: '',
    hint: '',
    choice_labels: {},
    choice_help: {},
    price_deltas: {},
    ...overrides,
  };
}

const CLEANING: DetailsSchema = {
  key: 'cleaning',
  fields: [
    field({
      name: 'property_type',
      type: 'choice',
      required: true,
      label: 'Property type',
      choices: ['APARTMENT', 'HOUSE', 'OFFICE'],
    }),
    field({ name: 'bedrooms', type: 'integer', required: true, label: 'Bedrooms', choices: null }),
    field({ name: 'depth', type: 'choice', required: true, label: 'Depth', choices: ['STANDARD', 'DEEP'] }),
    field({
      name: 'has_supplies',
      type: 'boolean',
      required: false,
      label: 'Customer provides supplies',
      choices: null,
    }),
    field({ name: 'note', type: 'char', required: false, label: 'Note', choices: null }),
  ],
};

const ERRANDS: DetailsSchema = {
  key: 'errands',
  fields: [field({ name: 'tasks', type: 'list', required: true, label: 'Tasks', choices: null })],
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
      fields: [field({ name: 'why', type: 'char', required: true, label: 'Why', choices: null })],
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
      fields: [field({ name: 'extras', type: 'list', required: false, label: 'Extras', choices: null })],
    };

    expect(toRequestDetails(schema, { extras: [] })).toEqual({});
  });

  it('keeps a required field even when blank, so the API reports it', () => {
    const details = toRequestDetails(CLEANING, { ...VALID, depth: '' });

    expect(details).toHaveProperty('depth');
  });
});

/**
 * Half-typed list entries.
 *
 * The old list field joined the array into a comma separated string and split it
 * back on every keystroke, so a trailing comma erased itself and anything typed
 * but not committed vanished on submit. These pin the replacement.
 */
describe('text typed but not added', () => {
  const BEAUTY: DetailsSchema = {
    key: 'beauty',
    fields: [
      field({ name: 'treatments', type: 'list', required: true, label: 'Treatments' }),
      field({ name: 'notes', type: 'char', required: false, label: 'Notes' }),
    ],
  };

  it('counts as an answer rather than being dropped', () => {
    const merged = withDrafts(BEAUTY, { treatments: [] }, { treatments: 'Box braids' });

    expect(merged.treatments).toEqual(['Box braids']);
  });

  it('is added after whatever was already committed', () => {
    const merged = withDrafts(BEAUTY, { treatments: ['Gel manicure'] }, { treatments: 'Pedicure' });

    expect(merged.treatments).toEqual(['Gel manicure', 'Pedicure']);
  });

  it('ignores whitespace that is not an answer', () => {
    const merged = withDrafts(BEAUTY, { treatments: ['Hair'] }, { treatments: '   ' });

    expect(merged.treatments).toEqual(['Hair']);
  });

  it('leaves non-list fields alone', () => {
    const merged = withDrafts(BEAUTY, { notes: 'careful' }, { notes: 'ignored' });

    expect(merged.notes).toBe('careful');
  });

  it('makes a single typed treatment pass validation on its own', () => {
    // The real failure this prevents: typing one treatment, tapping Book, and
    // being told the field is required.
    const schema = buildSpecSchema(BEAUTY);
    const merged = withDrafts(BEAUTY, { treatments: [], notes: '' }, { treatments: 'Box braids' });

    expect(schema.safeParse(merged).success).toBe(true);
  });

  it('still fails when nothing was typed at all', () => {
    const schema = buildSpecSchema(BEAUTY);
    const merged = withDrafts(BEAUTY, { treatments: [], notes: '' }, {});

    expect(schema.safeParse(merged).success).toBe(false);
  });
});

describe('what the answers add to the price', () => {
  const CLEAN: DetailsSchema = {
    key: 'cleaning',
    fields: [
      field({
        name: 'depth',
        type: 'choice',
        required: true,
        label: 'Depth',
        choices: ['STANDARD', 'DEEP'],
        price_deltas: { DEEP: 2_000_000 },
      }),
      field({
        name: 'express',
        type: 'boolean',
        required: false,
        label: 'Express',
        price_deltas: { true: 30_000 },
      }),
    ],
  };

  it('is nothing for the cheaper answer', () => {
    expect(optionsDeltaKobo(CLEAN, { depth: 'STANDARD' })).toBe(0);
  });

  it('is the quoted delta for the dearer one', () => {
    expect(optionsDeltaKobo(CLEAN, { depth: 'DEEP' })).toBe(2_000_000);
  });

  it('changes the moment the answer changes', () => {
    // The behaviour the footer depends on: no refetch, no debounce.
    expect(optionsDeltaKobo(CLEAN, { depth: 'STANDARD' })).toBe(0);
    expect(optionsDeltaKobo(CLEAN, { depth: 'DEEP' })).toBe(2_000_000);
  });

  it('counts a boolean only when it is true', () => {
    expect(optionsDeltaKobo(CLEAN, { express: false })).toBe(0);
    expect(optionsDeltaKobo(CLEAN, { express: true })).toBe(30_000);
  });

  it('adds up across fields', () => {
    expect(optionsDeltaKobo(CLEAN, { depth: 'DEEP', express: true })).toBe(2_030_000);
  });

  it('invents nothing when the server priced nothing', () => {
    // An option the spec knows about but nobody has priced. The app shows no
    // surcharge rather than guessing at one, and the total stays the base price.
    const unpriced: DetailsSchema = {
      key: 'laundry',
      fields: [field({ name: 'express', type: 'boolean', label: 'Express' })],
    };

    expect(optionsDeltaKobo(unpriced, { express: true })).toBe(0);
  });

  it('is nothing when there is no schema', () => {
    expect(optionsDeltaKobo(undefined, { depth: 'DEEP' })).toBe(0);
  });
});

/**
 * A booking that comes back rejected.
 *
 * Laundry was submitted three times and nothing appeared on screen: the button
 * stopped spinning and the form sat there. Two separate defects, both here.
 */
describe('a required number left blank', () => {
  const LAUNDRY: DetailsSchema = {
    key: 'laundry',
    fields: [
      field({ name: 'item_count', type: 'integer', required: true, label: 'Number of items' }),
      field({
        name: 'wash_type',
        type: 'choice',
        required: true,
        label: 'Wash type',
        choices: ['WASH_AND_FOLD', 'DRY_CLEAN'],
      }),
      field({ name: 'express', type: 'boolean', required: false, label: 'Express' }),
    ],
  };

  it('is refused before anything is sent', () => {
    // Number('') is 0, so a coercing schema accepted a blank field, the app sent
    // an empty string, and the server answered 400.
    const schema = buildSpecSchema(LAUNDRY);
    const result = schema.safeParse({
      item_count: '',
      wash_type: 'WASH_AND_FOLD',
      express: false,
    });

    expect(result.success).toBe(false);
  });

  it('says which field it is', () => {
    const schema = buildSpecSchema(LAUNDRY);
    const result = schema.safeParse({ item_count: '', wash_type: 'DRY_CLEAN', express: false });

    if (result.success) throw new Error('expected a failure');
    expect(result.error.issues[0].path[0]).toBe('item_count');
    expect(result.error.issues[0].message).toMatch(/number of items/i);
  });

  it('accepts a number typed as text', () => {
    const schema = buildSpecSchema(LAUNDRY);

    expect(
      schema.safeParse({ item_count: '5', wash_type: 'DRY_CLEAN', express: false }).success,
    ).toBe(true);
  });

  it('accepts an actual number', () => {
    const schema = buildSpecSchema(LAUNDRY);

    expect(
      schema.safeParse({ item_count: 5, wash_type: 'DRY_CLEAN', express: false }).success,
    ).toBe(true);
  });

  it('rejects text that is not a number', () => {
    const schema = buildSpecSchema(LAUNDRY);

    expect(
      schema.safeParse({ item_count: 'five', wash_type: 'DRY_CLEAN', express: false }).success,
    ).toBe(false);
  });

  it('still lets a complete laundry booking through', () => {
    const schema = buildSpecSchema(LAUNDRY);

    expect(
      schema.safeParse({ item_count: '12', wash_type: 'WASH_AND_FOLD', express: true }).success,
    ).toBe(true);
  });
});

describe('errors the server raised against the spec payload', () => {
  function rejection(fields: unknown) {
    return new ApiError({
      code: 'VALIDATION_ERROR',
      message: 'Please check the form.',
      status: 400,
      details: { fields },
    });
  }

  it('reaches the field it belongs to', () => {
    // They arrive nested under `details`, one level deeper than the generic form
    // mapper looks. That is why a rejected booking rendered nothing at all.
    const errors = toSpecFieldErrors(
      rejection({ details: { item_count: ['A valid integer is required.'] } }),
    );

    expect(errors).toEqual({ item_count: 'A valid integer is required.' });
  });

  it('shows only the first message per field', () => {
    const errors = toSpecFieldErrors(
      rejection({ details: { item_count: ['First problem.', 'Restatement.'] } }),
    );

    expect(errors.item_count).toBe('First problem.');
  });

  it('handles several fields at once', () => {
    const errors = toSpecFieldErrors(
      rejection({
        details: { item_count: ['Required.'], wash_type: ['Not a valid choice.'] },
      }),
    );

    expect(Object.keys(errors).sort()).toEqual(['item_count', 'wash_type']);
  });

  it('is empty for a rejection that is not about the spec', () => {
    expect(toSpecFieldErrors(rejection({ address_id: ['Unknown address.'] }))).toEqual({});
  });

  it('is empty for a failure that is not a validation error', () => {
    const offline = new ApiError({ code: 'NETWORK_UNAVAILABLE', message: 'No connection.' });

    expect(toSpecFieldErrors(offline)).toEqual({});
  });

  it('is empty for something that is not an api error at all', () => {
    expect(toSpecFieldErrors(new Error('boom'))).toEqual({});
    expect(toSpecFieldErrors(undefined)).toEqual({});
  });
});
