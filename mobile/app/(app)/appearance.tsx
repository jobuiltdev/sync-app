import { useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { Header } from '@/components/ui/Header';
import { Icon } from '@/components/ui/Icon';
import { ListRow, RowGroup } from '@/components/ui/ListRow';
import { Screen } from '@/components/ui/Screen';
import { Card } from '@/components/ui/Surface';
import { Text } from '@/components/ui/Text';
import {
  THEME_MODES,
  THEME_MODE_HINTS,
  THEME_MODE_LABELS,
  type ThemeMode,
  useTheme,
} from '@/theme/theme';
import { spacing } from '@/theme/tokens';

const ICONS: Record<ThemeMode, 'device' | 'sun' | 'moon'> = {
  system: 'device',
  light: 'sun',
  dark: 'moon',
};

/**
 * Appearance.
 *
 * A first-class setting rather than a toggle buried in a list. The choice
 * applies on the tap and persists, so the app it is next opened with is the app
 * that was chosen.
 *
 * Selection is marked by a check as well as by colour, because a selected row
 * distinguished only by an accent tint is not distinguishable to everybody.
 */
export default function AppearanceScreen() {
  const router = useRouter();
  const { mode, setMode, scheme, palette } = useTheme();

  return (
    <Screen>
      <Header onBack={() => router.back()} title="Appearance" />

      <View style={styles.body}>
        <Card padding="none">
          <RowGroup>
            {THEME_MODES.map((option) => {
              const selected = option === mode;

              return (
                <ListRow
                  key={option}
                  title={THEME_MODE_LABELS[option]}
                  subtitle={THEME_MODE_HINTS[option]}
                  icon={ICONS[option]}
                  iconTone={selected ? 'primary' : 'neutral'}
                  accessibilityLabel={`${THEME_MODE_LABELS[option]}. ${THEME_MODE_HINTS[option]}`}
                  onPress={() => setMode(option)}
                  trailing={
                    selected ? (
                      <Icon name="check" size={20} color={palette.primary} strokeWidth={2.4} />
                    ) : undefined
                  }
                />
              );
            })}
          </RowGroup>
        </Card>

        <Text variant="caption" tone="muted">
          {mode === 'system'
            ? `Following your device, which is currently ${scheme}.`
            : `Always ${scheme}, whatever your device is set to.`}
        </Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  body: { gap: spacing.md },
});
