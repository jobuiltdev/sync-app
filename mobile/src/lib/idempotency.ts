/**
 * Keys for retry-safe writes.
 *
 * A key has one job: let the server recognise the second copy of a request as
 * the same request. It does not need to be unguessable, because the server scopes
 * keys to the account that sent them, so one provider's key can never collide
 * with another's or be used to reach their records. That is why this does not
 * pull in a crypto module for a value that only has to be unique on one device.
 *
 * The important part is who holds it. A key generated once and reused for every
 * attempt at one payout is what makes the retry safe; a fresh key per attempt
 * would defeat the whole mechanism, so callers keep it in state rather than
 * calling this at the point of sending.
 */
export function newIdempotencyKey(): string {
  const time = Date.now().toString(36);
  const first = Math.random().toString(36).slice(2, 10);
  const second = Math.random().toString(36).slice(2, 10);

  return `${time}-${first}${second}`;
}
