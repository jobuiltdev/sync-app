import { Pressable, StyleSheet, View } from 'react-native';

import type { DetailsField, DetailsSchema } from '@/api/endpoints/catalog';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Icon } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import type { SpecValue } from '@/features/bookings/spec-form';
import { formatNaira } from '@/lib/money';
import { usePalette } from '@/theme/theme';
import { MIN_TOUCH_TARGET, radii, spacing } from '@/theme/tokens';

interface SpecFieldsProps {
  schema: DetailsSchema;
  values: Record<string, SpecValue>;
  errors: Record<string, string>;
  onChange: (name: string, value: SpecValue) => void;
  /** Text typed into a list field but not committed yet, by field name.
   *
   *  Held by the screen rather than by the field, because the screen is what
   *  folds it into the answers on submit. A second copy inside the field would
   *  be a second source of truth for the same characters, and the one that got
   *  submitted would not always be the one on screen. */
  drafts?: Record<string, string>;
  onDraftChange?: (name: string, draft: string) => void;
}

/**
 * Renders whatever the service asks for.
 *
 * Nothing here knows about cleaning or dispatch. The field list is served from
 * the service's spec, so a seventh vertical appears in the app with no release,
 * and hard-coding a single service's fields into a screen would give that up for
 * a slightly prettier form.
 *
 * Every word on screen comes from the API too: labels, help text, examples and
 * the descriptions under each choice. The app decides how a field looks, never
 * what it says.
 */
export function SpecFields({
  schema,
  values,
  errors,
  onChange,
  drafts,
  onDraftChange,
}: SpecFieldsProps) {
  return (
    <View style={styles.group}>
      {schema.fields.map((field) => (
        <SpecFieldRow
          key={field.name}
          field={field}
          value={values[field.name]}
          error={errors[field.name]}
          onChange={(value) => onChange(field.name, value)}
          draft={drafts?.[field.name] ?? ''}
          onDraftChange={(draft) => onDraftChange?.(field.name, draft)}
        />
      ))}
    </View>
  );
}

interface RowProps {
  field: DetailsField;
  value: SpecValue | undefined;
  error?: string;
  onChange: (value: SpecValue) => void;
  draft: string;
  onDraftChange?: (draft: string) => void;
}

function SpecFieldRow({ field, value, error, onChange, draft, onDraftChange }: RowProps) {
  const label = field.required ? field.label : `${field.label} (optional)`;

  if (field.type === 'boolean') {
    return <YesNoField field={field} label={label} value={Boolean(value)} onChange={onChange} />;
  }

  if (field.type === 'choice' && field.choices) {
    return <ChoiceField field={field} label={label} value={value} error={error} onChange={onChange} />;
  }

  if (field.type === 'list') {
    return (
      <ListField
        field={field}
        label={label}
        value={Array.isArray(value) ? value : []}
        error={error}
        onChange={onChange}
        draft={draft}
        onDraftChange={onDraftChange}
      />
    );
  }

  return (
    <Field
      label={label}
      value={value === undefined ? '' : String(value)}
      onChangeText={onChange}
      error={error}
      hint={field.help_text || undefined}
      placeholder={field.placeholder || undefined}
      multiline={field.style === 'multiline'}
      numberOfLines={field.style === 'multiline' ? 4 : undefined}
      keyboardType={field.type === 'integer' ? 'number-pad' : 'default'}
    />
  );
}

/**
 * A yes or no question, asked as one.
 *
 * A switch is right for a setting and wrong for a question. "Will the provider
 * need to buy anything for you?" with a toggle beside it leaves people unsure
 * which way is yes, and an untouched switch reads as a deliberate no.
 */
function YesNoField({
  field,
  label,
  value,
  onChange,
}: {
  field: DetailsField;
  label: string;
  value: boolean;
  onChange: (value: SpecValue) => void;
}) {
  const surcharge = field.price_deltas?.true ?? 0;

  return (
    <View style={styles.choiceGroup}>
      <Text variant="footnote" weight="medium" tone="soft">
        {label}
      </Text>
      {field.help_text ? (
        <Text variant="caption" tone="muted">
          {field.help_text}
        </Text>
      ) : null}
      <View style={styles.choices}>
        {[
          { answer: true, text: 'Yes' },
          { answer: false, text: 'No' },
        ].map(({ answer, text }) => (
          <Chip
            key={text}
            label={answer && surcharge ? `${text} (+${formatNaira(surcharge)})` : text}
            selected={value === answer}
            onPress={() => onChange(answer)}
          />
        ))}
      </View>
    </View>
  );
}

/**
 * One of several.
 *
 * Rendered as cards when the spec supplies a description per choice, because a
 * choice between "Standard" and "Deep" is not answerable from the words alone.
 */
function ChoiceField({
  field,
  label,
  value,
  error,
  onChange,
}: {
  field: DetailsField;
  label: string;
  value: SpecValue | undefined;
  error?: string;
  onChange: (value: SpecValue) => void;
}) {
  const palette = usePalette();
  const asCards = field.style === 'cards' || Object.keys(field.choice_help ?? {}).length > 0;

  return (
    <View style={styles.choiceGroup}>
      <Text variant="footnote" weight="medium" tone="soft">
        {label}
      </Text>
      {field.help_text ? (
        <Text variant="caption" tone="muted">
          {field.help_text}
        </Text>
      ) : null}

      <View style={asCards ? styles.cards : styles.choices}>
        {(field.choices ?? []).map((choice) => {
          const selected = value === choice;
          const text = field.choice_labels?.[choice] ?? humanise(choice);
          const help = field.choice_help?.[choice];
          const delta = field.price_deltas?.[choice] ?? 0;

          if (!asCards) {
            return (
              <Chip key={choice} label={text} selected={selected} onPress={() => onChange(choice)} />
            );
          }

          return (
            <Pressable
              key={choice}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              accessibilityLabel={delta ? `${text}, plus ${formatNaira(delta)}` : text}
              onPress={() => onChange(choice)}
              style={[
                styles.card,
                {
                  backgroundColor: selected ? palette.primarySoft : palette.surface,
                  borderColor: selected ? palette.primary : palette.hairline,
                  borderWidth: selected ? 2 : StyleSheet.hairlineWidth * 2,
                },
              ]}
            >
              <View style={styles.cardHead}>
                <Text
                  variant="body"
                  weight="semibold"
                  style={{ color: selected ? palette.onPrimarySoft : palette.ink }}
                >
                  {text}
                </Text>
                {delta ? (
                  <Text variant="footnote" weight="semibold" tone="primary">
                    +{formatNaira(delta)}
                  </Text>
                ) : null}
                {selected ? (
                  <Icon name="check" size={17} color={palette.primary} strokeWidth={2.4} />
                ) : null}
              </View>
              {help ? (
                <Text variant="caption" tone="muted">
                  {help}
                </Text>
              ) : null}
            </Pressable>
          );
        })}
      </View>

      {error ? (
        <Text variant="caption" tone="danger" accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

/**
 * A list of short things, typed one at a time.
 *
 * The previous version joined the list into a comma separated string and split
 * it back on every keystroke. Typing a comma erased itself, so the field could
 * not hold more than one entry, and any half-typed entry vanished on submit.
 *
 * Here the entries and the text being typed are separate. A comma still works
 * for anyone who expects it, Return works, the Add button works, and whatever is
 * left in the box when the form is submitted is handed up rather than dropped.
 */
function ListField({
  field,
  label,
  value,
  error,
  onChange,
  draft,
  onDraftChange,
}: {
  field: DetailsField;
  label: string;
  value: string[];
  error?: string;
  onChange: (value: SpecValue) => void;
  draft: string;
  onDraftChange?: (draft: string) => void;
}) {
  const palette = usePalette();

  function update(text: string) {
    // A comma is a convenience, not a requirement: it commits what precedes it
    // and leaves the rest in the box.
    if (!text.includes(',')) {
      onDraftChange?.(text);
      return;
    }

    const parts = text.split(',');
    const trailing = parts.pop() ?? '';
    const added = parts.map((part) => part.trim()).filter(Boolean);

    if (added.length) onChange([...value, ...added]);
    onDraftChange?.(trailing);
  }

  function commit() {
    const entry = draft.trim();
    if (!entry) return;
    onChange([...value, entry]);
    onDraftChange?.('');
  }

  function remove(index: number) {
    onChange(value.filter((_, i) => i !== index));
  }

  return (
    <View style={styles.choiceGroup}>
      {value.length > 0 ? (
        <View style={styles.entries}>
          {value.map((entry, index) => (
            <Pressable
              key={`${entry}-${index}`}
              accessibilityRole="button"
              accessibilityLabel={`Remove ${entry}`}
              onPress={() => remove(index)}
              style={[
                styles.entry,
                { backgroundColor: palette.primarySoft, borderColor: palette.primary },
              ]}
            >
              <Text variant="footnote" style={{ color: palette.onPrimarySoft }}>
                {entry}
              </Text>
              <Icon name="close" size={14} color={palette.onPrimarySoft} strokeWidth={2.4} />
            </Pressable>
          ))}
        </View>
      ) : null}

      <Field
        label={label}
        value={draft}
        onChangeText={update}
        onSubmitEditing={commit}
        blurOnSubmit={false}
        returnKeyType="done"
        error={error}
        hint={field.hint || field.help_text || undefined}
        placeholder={field.placeholder || undefined}
      />

      <View style={styles.addRow}>
        <Button label="Add" variant="secondary" onPress={commit} disabled={!draft.trim()} />
      </View>
    </View>
  );
}

function Chip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  const palette = usePalette();

  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      accessibilityLabel={label}
      onPress={onPress}
      style={[
        styles.choice,
        {
          backgroundColor: selected ? palette.primarySoft : palette.surface,
          borderColor: selected ? palette.primary : palette.hairline,
          borderWidth: selected ? 2 : StyleSheet.hairlineWidth * 2,
        },
      ]}
    >
      <Text
        variant="footnote"
        weight={selected ? 'semibold' : 'regular'}
        style={{ color: selected ? palette.onPrimarySoft : palette.inkSoft }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function humanise(choice: string): string {
  return choice.charAt(0) + choice.slice(1).toLowerCase().replace(/_/g, ' ');
}

const styles = StyleSheet.create({
  group: { gap: spacing.lg },
  choiceGroup: { gap: spacing.sm },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  choice: {
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    borderRadius: radii.pill,
  },
  cards: { gap: spacing.sm },
  card: { borderRadius: radii.card, padding: spacing.lg, gap: spacing.xxs },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  entries: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  entry: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: radii.pill,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  addRow: { alignSelf: 'flex-start' },
});
