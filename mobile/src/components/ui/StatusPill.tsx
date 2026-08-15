/**
 * A lifecycle status, rendered.
 *
 * Thin by design: the mapping from status to tone and wording lives in
 * `features/status/presentation`, where it is testable without a renderer, and
 * where four lifecycles can be kept consistent with each other.
 */

import { Pill } from '@/components/ui/Pill';
import type { StatusView } from '@/features/status/presentation';

export function StatusPill({ view }: { view: StatusView }) {
  return <Pill label={view.label} tone={view.tone} dot={view.live} />;
}
