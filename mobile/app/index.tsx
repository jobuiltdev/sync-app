import { useStartup } from '@/features/startup/hooks';
import { LaunchScreen } from '@/features/startup/LaunchScreen';

/**
 * The launch seam.
 *
 * Every cold start passes through here, and it is where the future launch
 * animation will live. It makes no decisions of its own: readiness and
 * destination both come from `useStartup`, which owns the three keychain reads
 * and the routing priority.
 *
 * Presentation and handoff timing live in `LaunchScreen`. Keeping that boundary
 * separate means motion can be added there later without duplicating readiness,
 * storage or destination logic in the route.
 */
export default function Index() {
  const { isReady, destination, motion } = useStartup();

  return <LaunchScreen isReady={isReady} destination={destination} motion={motion} />;
}
