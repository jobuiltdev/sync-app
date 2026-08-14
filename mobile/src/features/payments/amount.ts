/**
 * Turning what a provider types into what the API accepts.
 *
 * The field is in naira because that is what people think in. The wire is in
 * kobo because that is what money is in everywhere else in this system. The
 * conversion happens once, here, and only for whole naira, so there is no point
 * at which a fraction has to be rounded and no float is ever involved.
 */
import { formatNaira } from '@/lib/money';

/** Returns kobo, or null when the text is not a whole number of naira. */
export function toKobo(amount: string): number | null {
  const trimmed = amount.trim();
  if (!/^\d+$/.test(trimmed)) return null;

  return Number(trimmed) * 100;
}

/**
 * Local validation is a courtesy, not the rule.
 *
 * It saves an obviously doomed round trip on a slow connection. The server
 * decides, and when the two disagree the server is right: another device may
 * have spent the balance since this screen loaded.
 */
export function validateAmount(
  amount: string,
  availableKobo: number,
): { kobo: number | null; error: string | null } {
  const kobo = toKobo(amount);

  if (amount.trim().length === 0) return { kobo, error: 'Enter an amount.' };
  if (kobo === null) return { kobo, error: 'Enter a whole number of naira.' };
  if (kobo <= 0) return { kobo, error: 'Enter an amount greater than zero.' };
  if (kobo > availableKobo) {
    return { kobo, error: `That is more than your ${formatNaira(availableKobo)} balance.` };
  }

  return { kobo, error: null };
}
