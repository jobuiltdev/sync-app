import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';

import type { DetailsField, DetailsSchema } from '@/api/endpoints/catalog';
import { Field } from '@/components/ui/Field';
import type { SpecValue } from '@/features/bookings/spec-form';
import { MIN_TOUCH_TARGET, colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

interface SpecFieldsProps {
  schema: DetailsSchema;
  values: Record<string, SpecValue>;
  errors: Record<string, string>;
  onChange: (name: string, value: SpecValue) => void;
}

/** Renders whatever the service asks for. Nothing here knows about cleaning or
 *  dispatch; a new vertical appears on its own once the API serves its schema. */
export function SpecFields({ schema, values, errors, onChange }: SpecFieldsProps) {
  return (
    <View style={styles.group}>
      {schema.fields.map((field) => (
        <SpecFieldRow
          key={field.name}
          field={field}
          value={values[field.name]}
          error={errors[field.name]}
          onChange={(value) => onChange(field.name, value)}
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
}

function SpecFieldRow({ field, value, error, onChange }: RowProps) {
  const label = field.required ? field.label : `${field.label} (optional)`;

  if (field.type === 'boolean') {
    return (
      <View style={styles.switchRow}>
        <Text style={styles.switchLabel}>{label}</Text>
        <Switch
          accessibilityLabel={label}
          value={Boolean(value)}
          onValueChange={onChange}
          trackColor={{ true: colors.accent, false: colors.hairline }}
        />
      </View>
    );
  }

  if (field.type === 'choice' && field.choices) {
    return (
      <View style={styles.choiceGroup}>
        <Text style={styles.label}>{label}</Text>
        <View style={styles.choices}>
          {field.choices.map((choice) => {
            const selected = value === choice;
            return (
              <Pressable
                key={choice}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                onPress={() => onChange(choice)}
                style={[styles.choice, selected && styles.choiceSelected]}
              >
                <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>
                  {humanise(choice)}
                </Text>
              </Pressable>
            );
          })}
        </View>
        {error ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {error}
          </Text>
        ) : null}
      </View>
    );
  }

  if (field.type === 'list') {
    const text = Array.isArray(value) ? value.join(', ') : '';
    return (
      <Field
        label={label}
        value={text}
        onChangeText={(next) =>
          onChange(
            next
              .split(',')
              .map((part) => part.trim())
              .filter(Boolean),
          )
        }
        error={error}
        placeholder="Separate each one with a comma"
      />
    );
  }

  return (
    <Field
      label={label}
      value={value === undefined ? '' : String(value)}
      onChangeText={onChange}
      error={error}
      keyboardType={field.type === 'integer' ? 'number-pad' : 'default'}
    />
  );
}

function humanise(choice: string): string {
  return choice.charAt(0) + choice.slice(1).toLowerCase().replace(/_/g, ' ');
}

const styles = StyleSheet.create({
  group: { gap: spacing.lg },
  label: {
    fontSize: fontSizes.footnote,
    fontWeight: fontWeights.medium,
    color: colors.inkSoft,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: MIN_TOUCH_TARGET,
    gap: spacing.md,
  },
  switchLabel: { fontSize: fontSizes.body, color: colors.ink, flexShrink: 1 },
  choiceGroup: { gap: spacing.sm },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  choice: {
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.hairline,
    backgroundColor: colors.surface,
  },
  choiceSelected: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  choiceText: { fontSize: fontSizes.footnote, color: colors.inkSoft },
  choiceTextSelected: { color: colors.accent, fontWeight: fontWeights.semibold },
  error: { fontSize: fontSizes.caption, color: colors.danger },
});
