/**
 * Naira formatting.
 *
 * Money crosses the API as an integer number of kobo and is only ever turned into
 * a string here. Doing it at call sites is how two screens end up disagreeing
 * about whether a price includes a decimal.
 */

const NAIRA = '₦';

export function formatNaira(kobo: number, options: { showKobo?: boolean } = {}): string {
  const { showKobo = false } = options;
  const naira = kobo / 100;

  const formatted = naira.toLocaleString('en-NG', {
    minimumFractionDigits: showKobo ? 2 : 0,
    maximumFractionDigits: showKobo ? 2 : 0,
  });

  return `${NAIRA}${formatted}`;
}

/** How a price should read before a quote exists, which depends on how the
 *  service is priced rather than on the number itself. */
export function formatPriceFrom(kobo: number, pricingModel: string): string {
  if (pricingModel === 'QUOTE_ON_SITE') return 'Quoted after inspection';
  if (kobo <= 0) return 'Price on request';

  const price = formatNaira(kobo);
  switch (pricingModel) {
    case 'FIXED':
      return price;
    case 'PER_HOUR':
      return `${price} per hour`;
    case 'PER_ITEM':
      return `${price} per item`;
    default:
      return `From ${price}`;
  }
}
