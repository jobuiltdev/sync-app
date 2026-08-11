import { ApiError } from '@/api/errors';

/**
 * Turns an API failure into per-field messages plus one banner message.
 *
 * The server is the authority on validation. Mirroring its rules in the client
 * would mean two sets of rules to keep in step, so the client's job is to display
 * what came back rather than to predict it.
 */
export interface FormErrors {
  fields: Record<string, string>;
  message: string | null;
}

const EMPTY: FormErrors = { fields: {}, message: null };

export function toFormErrors(error: unknown): FormErrors {
  if (!(error instanceof ApiError)) return EMPTY;

  if (error.code === 'VALIDATION_ERROR') {
    const raw = (error.details.fields ?? {}) as Record<string, unknown>;
    const fields: Record<string, string> = {};

    for (const [name, messages] of Object.entries(raw)) {
      // DRF returns a list per field. Only the first is worth showing; the rest
      // are usually restatements of the same problem.
      const first = Array.isArray(messages) ? messages[0] : messages;
      if (typeof first === 'string') fields[name] = first;
    }

    // Errors raised against the payload as a whole have no field to attach to and
    // would otherwise vanish silently.
    const { non_field_errors: nonField, ...rest } = fields;
    return { fields: rest, message: nonField ?? null };
  }

  return { fields: {}, message: error.message };
}
