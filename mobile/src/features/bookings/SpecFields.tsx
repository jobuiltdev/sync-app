import { Pressable, StyleSheet, Switch, View } from 'react-native';

import type { DetailsField, DetailsSchema } from '@/api/endpoints/catalog';
import { Field } from '@/components/ui/Field';
import { Text } from '@/components/ui/Text';
import type { SpecValue } from '@/features/bookings/spec-form';
import { usePalette } from '@/theme/theme';
import { MIN_TOUCH_TARGET, radii, spacing } from '@/theme/tokens';

interface SpecFieldsProps {
  schema: DetailsSchema;
  values: Record<string, SpecValue>;
  errors: Record<string, string>;
  onChange: (name: string, value: SpecValue) => void;
}

/**
 * Renders whatever the service asks for.
 *
 * Nothing here knows about cleaning or dispatch. The field list is served from
 * the service's spec, so a seventh vertical appears in the app with no release,
 * and hard-coding a single service's fields into a screen would give that up for
 * a slightly prettier form.
 */
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
  const palette = usePalette();
  const label = field.required ? field.label : `${field.label} (optional)`;

  if (field.type === 'boolean') {
    return (
      <View style={styles.switchRow}>
        <Text variant="body" style={styles.switchLabel}>
          {label}
        </Text>
        <Switch
          accessibilityLabel={label}
          value={Boolean(value)}
          onValueChange={onChange}
          trackColor={{ true: palette.primary, false: palette.hairline }}
          thumbColor={palette.surface}
        />
      </View>
    );
  }

  if (field.type === 'choice' && field.choices) {
    return (
      <View style={styles.choiceGroup}>
        <Text variant="footnote" weight="medium" tone="soft">
          {label}
        </Text>
        <View style={styles.choices}>
          {field.choices.map((choice) => {
            const selected = value === choice;

            return (
              <Pressable
                key={choice}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                accessibilityLabel={humanise(choice)}
                onPress={() => onChange(choice)}
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
                  {humanise(choice)}
                </Text>
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
        hint="Separate each one with a comma"
        placeholder="Bread, milk, airtime"
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
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: MIN_TOUCH_TARGET,
    gap: spacing.md,
  },
  switchLabel: { flexShrink: 1 },
  choiceGroup: { gap: spacing.sm },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  choice: {
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    borderRadius: radii.pill,
  },
});
