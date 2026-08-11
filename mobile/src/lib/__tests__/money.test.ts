import { formatNaira, formatPriceFrom } from '@/lib/money';

describe('formatNaira', () => {
  it('converts kobo to naira', () => {
    expect(formatNaira(1_500_000)).toBe('₦15,000');
  });

  it('omits kobo by default, since prices here are rarely sub-naira', () => {
    expect(formatNaira(1_500_050)).toBe('₦15,001');
  });

  it('shows kobo when asked', () => {
    expect(formatNaira(1_500_050, { showKobo: true })).toBe('₦15,000.50');
  });

  it('groups thousands', () => {
    expect(formatNaira(250_000_000)).toBe('₦2,500,000');
  });

  it('handles zero', () => {
    expect(formatNaira(0)).toBe('₦0');
  });
});

describe('formatPriceFrom', () => {
  it('shows a fixed price as a price', () => {
    expect(formatPriceFrom(1_500_000, 'FIXED')).toBe('₦15,000');
  });

  it('qualifies an hourly rate', () => {
    expect(formatPriceFrom(500_000, 'PER_HOUR')).toBe('₦5,000 per hour');
  });

  it('qualifies a per-item rate', () => {
    expect(formatPriceFrom(50_000, 'PER_ITEM')).toBe('₦500 per item');
  });

  it('treats a distance price as a starting point', () => {
    expect(formatPriceFrom(120_000, 'DISTANCE')).toBe('From ₦1,200');
  });

  it('never shows a number for a service quoted on site', () => {
    // Showing a figure that the provider will then contradict in person is worse
    // than showing none.
    expect(formatPriceFrom(500_000, 'QUOTE_ON_SITE')).toBe('Quoted after inspection');
  });

  it('does not show a free price for a service with no base price set', () => {
    expect(formatPriceFrom(0, 'FIXED')).toBe('Price on request');
  });
});
