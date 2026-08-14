import { z } from 'zod';

/**
 * What the registration form insists on before it will send anything.
 *
 * Shape only. Password strength, email uniqueness, whether a phone number is
 * actually dialable and whether it is already taken are all the server's rules,
 * and duplicating any of them would mean two places to keep in step.
 *
 * A phone number is required. Booking needs a verified phone, and an account
 * with no number on file cannot even begin that: it is a form away rather than a
 * code away. Requiring the number is not the same as requiring it verified,
 * which stays progressive and is still demanded only at the first action that
 * needs it.
 */
export const registerSchema = z.object({
  first_name: z.string().trim().min(1, 'Enter your first name.'),
  last_name: z.string().trim().min(1, 'Enter your last name.'),
  email: z.email('Enter a valid email address.'),
  phone: z
    .string()
    .trim()
    .min(1, 'Enter your phone number.')
    // Deliberately loose: count the digits and nothing more. The server parses
    // the number properly and normalises it to E.164, so a stricter pattern here
    // would reject numbers the API would have accepted. Ten digits is the
    // shortest a Nigerian number can be written as, in the 0803 form.
    .refine((value) => value.replace(/\D/g, '').length >= 10, 'Enter a full phone number.'),
  password: z.string().min(1, 'Choose a password.'),
});

export type RegisterFormValues = z.infer<typeof registerSchema>;
