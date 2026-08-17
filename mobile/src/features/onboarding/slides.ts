/**
 * What Sync is, said four times.
 *
 * Shown once, on first launch, before anybody is asked for anything. The order
 * is deliberate: what you can get, who does it, what it costs you to find out,
 * and then the ask. Somebody who swipes through this should be able to explain
 * the product to a friend.
 *
 * Content lives here rather than in the screen so the copy is reviewable on its
 * own and the screen stays a carousel rather than a wall of strings.
 */

import type { IconName } from '@/components/ui/Icon';

export interface Slide {
  key: string;
  icon: IconName;
  /** A second and third glyph, arranged around the first. Cheaper than an
   *  illustration and it cannot go out of date with the catalog. */
  supporting: [IconName, IconName];
  title: string;
  body: string;
}

export const SLIDES: Slide[] = [
  {
    key: 'services',
    icon: 'briefcase',
    supporting: ['dispatch', 'cleaning'],
    title: 'Everything you need,\nin one app',
    body: 'Courier, cleaning, errands, home repairs, beauty and laundry. Book any of them from one place, on your time.',
  },
  {
    key: 'providers',
    icon: 'shield',
    supporting: ['profile', 'star'],
    title: 'People you can\ntrust',
    body: 'Every provider is reviewed before they can take a job. You see who is coming, and what the work costs, before you book.',
  },
  {
    key: 'price',
    icon: 'wallet',
    supporting: ['card', 'check'],
    title: 'The price you agree\nis the price you pay',
    body: 'Fixed when you book and unchanged after. Pay securely in the app, and your money is only released once the work is done.',
  },
  {
    key: 'work',
    icon: 'clock',
    supporting: ['pin', 'bell'],
    title: 'Follow it from\nstart to finish',
    body: 'See when a provider takes your job, when they set off, and when the work is done. You confirm it, not them.',
  },
];

/** Whether the carousel has been seen. Stored so it happens once, not on every
 *  cold start, which would be an advert rather than an introduction. */
export const ONBOARDING_STORAGE_KEY = 'sync.onboarding_seen';
