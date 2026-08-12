import { z } from 'zod';

import type { DetailsField, DetailsSchema } from '@/api/endpoints/catalog';

/**
 * Turns a service's field schema into a form.
 *
 * The fields come from the API, which serves them from the spec registered for
 * the service. Hard-coding a form per category would mean a new vertical needs a
 * new app release, which is the thing the spec system exists to avoid.
 */

export type SpecValue = string | number | boolean | string[];

function fieldSchema(field: DetailsField): z.ZodTypeAny {
  switch (field.type) {
    case 'boolean':
      return z.boolean();

    case 'integer':
      // Text inputs hand back strings, so coerce before validating.
      return z.coerce.number({ error: `${field.label} must be a number.` }).int();

    case 'choice':
      return field.choices && field.choices.length > 0
        ? z.enum(field.choices as [string, ...string[]], {
            error: `Choose a ${field.label.toLowerCase()}.`,
          })
        : z.string();

    case 'list':
      return z.array(z.string().trim().min(1));

    default:
      return z.string();
  }
}

export function buildSpecSchema(schema: DetailsSchema | undefined): z.ZodType {
  if (!schema) return z.object({});

  const shape: Record<string, z.ZodTypeAny> = {};

  for (const field of schema.fields) {
    let rule = fieldSchema(field);

    if (field.required) {
      // A blank string satisfies z.string() but is not an answer.
      if (field.type === 'char') rule = z.string().trim().min(1, `${field.label} is required.`);
      if (field.type === 'list') rule = z.array(z.string().trim().min(1)).min(1);
    } else {
      rule = rule.optional();
    }

    shape[field.name] = rule;
  }

  return z.object(shape);
}

export function initialSpecValues(schema: DetailsSchema | undefined): Record<string, SpecValue> {
  if (!schema) return {};

  const values: Record<string, SpecValue> = {};

  for (const field of schema.fields) {
    switch (field.type) {
      case 'boolean':
        values[field.name] = false;
        break;
      case 'list':
        values[field.name] = [];
        break;
      case 'choice':
        // Left blank rather than defaulted to the first option, so an untouched
        // choice is visibly unanswered instead of silently answered.
        values[field.name] = '';
        break;
      default:
        values[field.name] = '';
    }
  }

  return values;
}

/** Strips blanks the user never filled in, so optional fields are omitted rather
 *  than sent as empty strings the backend would reject. */
export function toRequestDetails(
  schema: DetailsSchema | undefined,
  values: Record<string, SpecValue>,
): Record<string, unknown> {
  if (!schema) return {};

  const details: Record<string, unknown> = {};

  for (const field of schema.fields) {
    const value = values[field.name];

    if (value === '' || value === undefined) {
      if (field.required) details[field.name] = value;
      continue;
    }

    if (Array.isArray(value) && value.length === 0 && !field.required) continue;

    details[field.name] = field.type === 'integer' ? Number(value) : value;
  }

  return details;
}
