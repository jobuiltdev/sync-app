import { useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import type { Address } from '@/api/endpoints/addresses';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Header } from '@/components/ui/Header';
import { Icon } from '@/components/ui/Icon';
import { ListRow, RowGroup } from '@/components/ui/ListRow';
import { Pill } from '@/components/ui/Pill';
import { Screen } from '@/components/ui/Screen';
import { Sheet } from '@/components/ui/Sheet';
import { SkeletonList } from '@/components/ui/Skeleton';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { EmptyState, ErrorState, InlineError } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { useAddresses, useCreateAddress, useDeleteAddress } from '@/features/catalog/hooks';
import { NIGERIAN_STATES, stateLabel } from '@/lib/nigeria';
import { usePalette } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

/**
 * Where work happens.
 *
 * **The landmark is not secondary here.** Street addressing in much of Nigeria
 * is unreliable or absent, and a provider finds a place by "opposite the Eko
 * Hotel gate" far more often than by a house number. So the landmark is required
 * by the API, and this screen gives it equal visual weight rather than treating
 * it as an optional extra line.
 */
export default function AddressesScreen() {
  const router = useRouter();
  const addresses = useAddresses();
  const remove = useDeleteAddress();
  const [adding, setAdding] = useState(false);

  const saved = addresses.data?.results ?? [];

  return (
    <Screen refreshing={addresses.isRefetching} onRefresh={() => void addresses.refetch()}>
      <Header
        onBack={() => router.back()}
        title="Addresses"
        action={
          saved.length > 0 ? (
            <Button
              label="Add"
              icon="plus"
              variant="secondary"
              size="compact"
              fullWidth={false}
              onPress={() => setAdding(true)}
            />
          ) : undefined
        }
      />

      {addresses.isPending ? (
        <SkeletonList rows={2} showPlate={false} />
      ) : addresses.error ? (
        <ErrorState error={addresses.error} onRetry={() => void addresses.refetch()} />
      ) : saved.length === 0 ? (
        <EmptyState
          icon="pin"
          title="No addresses yet"
          body="Add the places you want work done. A landmark helps your provider find you."
          action={<Button label="Add an address" fullWidth={false} onPress={() => setAdding(true)} />}
        />
      ) : (
        <View style={styles.section}>
          <SectionHeader title={`${saved.length} saved`} />
          <Card padding="none">
            <RowGroup>
              {saved.map((address) => (
                <AddressRow
                  key={address.id}
                  address={address}
                  onDelete={() => remove.mutate(address.id)}
                  deleting={remove.isPending && remove.variables === address.id}
                />
              ))}
            </RowGroup>
          </Card>
        </View>
      )}

      <InlineError error={remove.error} />

      <AddAddressSheet visible={adding} onClose={() => setAdding(false)} />
    </Screen>
  );
}

function AddressRow({
  address,
  onDelete,
  deleting,
}: {
  address: Address;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <ListRow
      title={address.street_address}
      // The landmark is the subtitle rather than buried in meta, because it is
      // what a provider actually navigates by.
      subtitle={address.landmark}
      meta={[address.area, address.lga, stateLabel(address.state)].filter(Boolean).join(', ')}
      icon="pin"
      iconTone={address.is_default ? 'primary' : 'neutral'}
      accessibilityLabel={`${address.street_address}, ${address.landmark}${address.is_default ? ', default' : ''}`}
      trailing={
        <View style={styles.rowTrailing}>
          {address.is_default ? <Pill label="Default" tone="primary" /> : null}
          <Button
            label={deleting ? 'Removing' : 'Remove'}
            variant="ghost"
            size="compact"
            fullWidth={false}
            loading={deleting}
            onPress={onDelete}
          />
        </View>
      }
    />
  );
}

/**
 * Adding an address, in a sheet.
 *
 * A sheet rather than a route: it is one short form belonging to the list behind
 * it, and pushing a screen for it would lose the list's scroll position on the
 * way back.
 */
function AddAddressSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const palette = usePalette();
  const create = useCreateAddress();

  const [street, setStreet] = useState('');
  const [landmark, setLandmark] = useState('');
  const [area, setArea] = useState('');
  const [lga, setLga] = useState('');
  const [state, setState] = useState('LAGOS');
  const [directions, setDirections] = useState('');
  const [pickingState, setPickingState] = useState(false);

  const submit = () => {
    create.mutate(
      {
        street_address: street.trim(),
        landmark: landmark.trim(),
        area: area.trim(),
        lga: lga.trim(),
        state,
        directions_note: directions.trim(),
      },
      {
        onSuccess: () => {
          setStreet('');
          setLandmark('');
          setArea('');
          setLga('');
          setDirections('');
          onClose();
        },
      },
    );
  };

  return (
    <>
      <Sheet
        visible={visible && !pickingState}
        onClose={onClose}
        title="Add an address"
        subtitle="The landmark matters most. It is how your provider finds you."
      >
        <View style={styles.form}>
          <InlineError error={create.error} />

          <Field
            label="Street address"
            value={street}
            onChangeText={setStreet}
            placeholder="14 Adeola Odeku Street"
          />
          <Field
            label="Landmark"
            value={landmark}
            onChangeText={setLandmark}
            hint="Opposite, beside or behind something well known"
            placeholder="Opposite the Eko Hotel gate"
          />
          <Field label="Area" value={area} onChangeText={setArea} placeholder="Victoria Island" />
          <Field label="LGA" value={lga} onChangeText={setLga} placeholder="Eti-Osa" />

          <View style={styles.stateField}>
            <Text variant="footnote" weight="medium" tone="soft">
              State
            </Text>
            <Button
              label={stateLabel(state)}
              variant="secondary"
              icon="chevronDown"
              onPress={() => setPickingState(true)}
            />
          </View>

          <Field
            label="Directions (optional)"
            value={directions}
            onChangeText={setDirections}
            placeholder="Blue gate, second floor"
            multiline
          />

          <Button label="Save address" loading={create.isPending} onPress={submit} />
        </View>
      </Sheet>

      <Sheet
        visible={pickingState}
        onClose={() => setPickingState(false)}
        title="Choose a state"
      >
        {NIGERIAN_STATES.map((option) => (
          <ListRow
            key={option.value}
            title={option.label}
            accessibilityLabel={option.label}
            onPress={() => {
              setState(option.value);
              setPickingState(false);
            }}
            trailing={
              option.value === state ? (
                <Icon name="check" size={19} color={palette.primary} strokeWidth={2.4} />
              ) : undefined
            }
          />
        ))}
      </Sheet>
    </>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.md },
  rowTrailing: { alignItems: 'flex-end', gap: spacing.xs },
  form: { gap: spacing.lg, paddingTop: spacing.xs },
  stateField: { gap: spacing.sm },
});
