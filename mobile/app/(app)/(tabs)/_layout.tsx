import { Tabs, usePathname, useRouter } from 'expo-router';

import { TabBar, type TabItem } from '@/components/navigation/TabBar';
import { useActivityAttention } from '@/features/activity/hooks';

/**
 * The three destinations.
 *
 * Home, Activity, Profile, and deliberately nothing else. Addresses, payments,
 * earnings, the provider profile and appearance all reached this milestone as
 * candidates for a tab, and every one of them is a place you go occasionally
 * with a purpose rather than a place you live. Those belong behind Profile.
 *
 * A tab bar earns its space by being the thing you switch between constantly.
 * Six tabs is a menu wearing a tab bar's clothes.
 *
 * There is one navigation system for both roles. A provider is usually also a
 * customer, and giving them a second bar when they have a provider profile
 * would mean the app rearranging itself under someone who has just signed up to
 * offer a service. Activity adapts its contents instead.
 */
export default function TabsLayout() {
  const router = useRouter();
  const pathname = usePathname();
  const attention = useActivityAttention();

  const items: TabItem[] = [
    { key: 'home', label: 'Home', icon: 'home' },
    { key: 'activity', label: 'Activity', icon: 'activity', badge: attention },
    { key: 'profile', label: 'Profile', icon: 'profile' },
  ];

  const active = items.find((item) => pathname.startsWith(`/${item.key}`))?.key ?? 'home';

  return (
    <Tabs
      screenOptions={{ headerShown: false, animation: 'shift' }}
      tabBar={() => (
        <TabBar
          items={items}
          activeKey={active}
          onSelect={(key) => router.navigate(`/${key}` as never)}
        />
      )}
    >
      <Tabs.Screen name="home" />
      <Tabs.Screen name="activity" />
      <Tabs.Screen name="profile" />
    </Tabs>
  );
}
