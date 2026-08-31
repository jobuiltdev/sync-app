/**
 * The booking form's field renderer.
 *
 * These cover the interactions that were broken rather than the layout: a list
 * field that erased commas as you typed them, a yes or no question asked with a
 * switch, and choices shown as bare words when they needed explaining.
 */

import { cleanup, fireEvent } from '@testing-library/react-native';

import type { DetailsField, DetailsSchema } from '@/api/endpoints/catalog';
import { SpecFields } from '@/features/bookings/SpecFields';
import { renderWithProviders } from '@/test-utils/render';

function field(
  overrides: Partial<DetailsField> & Pick<DetailsField, 'name' | 'type'>,
): DetailsField {
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

// Each test mounts its own tree. Without an explicit teardown the previous one
// is still mounted when the next render starts, which React reports as
// overlapping act() calls and which leaves every query after the first failing.
afterEach(cleanup);

async function show(
  fields: DetailsField[],
  values: Record<string, unknown> = {},
  drafts: Record<string, string> = {},
) {
  const onChange = jest.fn();
  const onDraftChange = jest.fn();
  const schema: DetailsSchema = { key: 'test', fields };

  const view = await renderWithProviders(
    <SpecFields
      schema={schema}
      values={values as never}
      errors={{}}
      onChange={onChange}
      drafts={drafts}
      onDraftChange={onDraftChange}
    />,
  );

  return { view, onChange, onDraftChange };
}

describe('a list field', () => {
  const TREATMENTS = field({
    name: 'treatments',
    type: 'list',
    required: true,
    label: 'Treatments',
    placeholder: 'Box braids',
    hint: 'Add each treatment separately.',
  });

  it('accepts text with no comma in it', async () => {
    // The old field split on every keystroke, so a single word only survived by
    // accident and a trailing comma deleted itself.
    const { view, onDraftChange } = await show([TREATMENTS], { treatments: [] });

    fireEvent.changeText(view.getByPlaceholderText('Box braids'), 'Box braids');

    expect(onDraftChange).toHaveBeenLastCalledWith('treatments', 'Box braids');
  });

  it('commits an entry when Return is pressed', async () => {
    const { view, onChange } = await show([TREATMENTS], { treatments: [] }, {
      treatments: 'Box braids',
    });

    fireEvent(view.getByPlaceholderText('Box braids'), 'submitEditing');

    expect(onChange).toHaveBeenCalledWith('treatments', ['Box braids']);
  });

  it('commits an entry from the Add control', async () => {
    const { view, onChange } = await show([TREATMENTS], { treatments: [] }, {
      treatments: 'Pedicure',
    });

    fireEvent.press(view.getByText('Add'));

    expect(onChange).toHaveBeenCalledWith('treatments', ['Pedicure']);
  });

  it('still treats a comma as a separator for anyone who expects it', async () => {
    const { view, onChange } = await show([TREATMENTS], { treatments: [] });

    fireEvent.changeText(view.getByPlaceholderText('Box braids'), 'Box braids,');

    expect(onChange).toHaveBeenCalledWith('treatments', ['Box braids']);
  });

  it('keeps what follows a comma in the box', async () => {
    const { view, onDraftChange } = await show([TREATMENTS], { treatments: [] });

    fireEvent.changeText(view.getByPlaceholderText('Box braids'), 'Box braids, Ped');

    expect(onDraftChange).toHaveBeenLastCalledWith('treatments', ' Ped');
  });

  it('shows what has been added so far', async () => {
    const { view } = await show([TREATMENTS], { treatments: ['Box braids', 'Pedicure'] });

    expect(view.getByText('Box braids')).toBeTruthy();
    expect(view.getByText('Pedicure')).toBeTruthy();
  });

  it('removes an entry when it is tapped', async () => {
    const { view, onChange } = await show([TREATMENTS], { treatments: ['Box braids', 'Pedicure'] });

    fireEvent.press(view.getByLabelText('Remove Box braids'));

    expect(onChange).toHaveBeenCalledWith('treatments', ['Pedicure']);
  });

  it('shows the example the service supplied, not a shopping list', async () => {
    const { view } = await show([TREATMENTS], { treatments: [] });

    expect(view.getByPlaceholderText('Box braids')).toBeTruthy();
    expect(view.queryByPlaceholderText(/bread/i)).toBeNull();
    expect(view.queryByText(/separate each one with a comma/i)).toBeNull();
  });
});

describe('a yes or no question', () => {
  const PURCHASE = field({
    name: 'requires_purchase',
    type: 'boolean',
    label: 'Will the provider need to buy anything for you?',
    style: 'yes_no',
    help_text: 'The cost of whatever they buy is separate from the service fee.',
  });

  it('is asked as two answers rather than a switch', async () => {
    const { view } = await show([PURCHASE], { requires_purchase: false });

    expect(view.getByLabelText('Yes')).toBeTruthy();
    expect(view.getByLabelText('No')).toBeTruthy();
  });

  it('shows the question in full', async () => {
    const { view } = await show([PURCHASE], { requires_purchase: false });

    expect(view.getByText(/will the provider need to buy anything/i)).toBeTruthy();
    expect(view.queryByText(/requires purchase/i)).toBeNull();
  });

  it('explains that purchases are separate from the fee', async () => {
    const { view } = await show([PURCHASE], { requires_purchase: false });

    expect(view.getByText(/separate from the service fee/i)).toBeTruthy();
  });

  it('records the answer', async () => {
    const { view, onChange } = await show([PURCHASE], { requires_purchase: false });

    fireEvent.press(view.getByLabelText('Yes'));

    expect(onChange).toHaveBeenCalledWith('requires_purchase', true);
  });

  it('names a surcharge on the answer that carries one', async () => {
    const { view } = await show([field({ ...PURCHASE, price_deltas: { true: 30_000 } })], {});

    expect(view.getByText(/Yes \(\+₦300\)/)).toBeTruthy();
  });
});

describe('a choice that needs explaining', () => {
  const DEPTH = field({
    name: 'depth',
    type: 'choice',
    required: true,
    label: 'Cleaning depth',
    choices: ['STANDARD', 'DEEP'],
    style: 'cards',
    choice_labels: { STANDARD: 'Standard cleaning', DEEP: 'Deep cleaning' },
    choice_help: {
      STANDARD: 'Routine upkeep.',
      DEEP: 'Everything in a standard clean, plus the places it skips.',
    },
    price_deltas: { DEEP: 2_000_000 },
  });

  it('shows both options with their descriptions', async () => {
    const { view } = await show([DEPTH], { depth: '' });

    expect(view.getByText('Standard cleaning')).toBeTruthy();
    expect(view.getByText('Deep cleaning')).toBeTruthy();
    expect(view.getByText('Routine upkeep.')).toBeTruthy();
    expect(view.getByText(/plus the places it skips/i)).toBeTruthy();
  });

  it('shows what the dearer option adds', async () => {
    const { view } = await show([DEPTH], { depth: '' });

    expect(view.getByText('+₦20,000')).toBeTruthy();
  });

  it('records the choice', async () => {
    const { view, onChange } = await show([DEPTH], { depth: '' });

    fireEvent.press(view.getByLabelText(/Deep cleaning/));

    expect(onChange).toHaveBeenCalledWith('depth', 'DEEP');
  });

  it('uses the label the server supplied over the raw value', async () => {
    const { view } = await show([DEPTH], { depth: '' });

    expect(view.queryByText('DEEP')).toBeNull();
  });
});
