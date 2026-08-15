/**
 * Nigerian states, as the API names them.
 *
 * Mirrors apps/common/nigeria.NigerianState. A list of thirty-seven strings that
 * changes when the country does, which is to say not at all in the life of this
 * product, so it is inlined rather than fetched: a screen that cannot render its
 * area picker until a request returns is a worse trade than a list to update the
 * day a state is created.
 */
export interface NigerianState {
  value: string;
  label: string;
}

export const NIGERIAN_STATES: NigerianState[] = [
  { value: 'ABIA', label: 'Abia' },
  { value: 'ADAMAWA', label: 'Adamawa' },
  { value: 'AKWA_IBOM', label: 'Akwa Ibom' },
  { value: 'ANAMBRA', label: 'Anambra' },
  { value: 'BAUCHI', label: 'Bauchi' },
  { value: 'BAYELSA', label: 'Bayelsa' },
  { value: 'BENUE', label: 'Benue' },
  { value: 'BORNO', label: 'Borno' },
  { value: 'CROSS_RIVER', label: 'Cross River' },
  { value: 'DELTA', label: 'Delta' },
  { value: 'EBONYI', label: 'Ebonyi' },
  { value: 'EDO', label: 'Edo' },
  { value: 'EKITI', label: 'Ekiti' },
  { value: 'ENUGU', label: 'Enugu' },
  { value: 'FCT', label: 'Federal Capital Territory' },
  { value: 'GOMBE', label: 'Gombe' },
  { value: 'IMO', label: 'Imo' },
  { value: 'JIGAWA', label: 'Jigawa' },
  { value: 'KADUNA', label: 'Kaduna' },
  { value: 'KANO', label: 'Kano' },
  { value: 'KATSINA', label: 'Katsina' },
  { value: 'KEBBI', label: 'Kebbi' },
  { value: 'KOGI', label: 'Kogi' },
  { value: 'KWARA', label: 'Kwara' },
  { value: 'LAGOS', label: 'Lagos' },
  { value: 'NASARAWA', label: 'Nasarawa' },
  { value: 'NIGER', label: 'Niger' },
  { value: 'OGUN', label: 'Ogun' },
  { value: 'ONDO', label: 'Ondo' },
  { value: 'OSUN', label: 'Osun' },
  { value: 'OYO', label: 'Oyo' },
  { value: 'PLATEAU', label: 'Plateau' },
  { value: 'RIVERS', label: 'Rivers' },
  { value: 'SOKOTO', label: 'Sokoto' },
  { value: 'TARABA', label: 'Taraba' },
  { value: 'YOBE', label: 'Yobe' },
  { value: 'ZAMFARA', label: 'Zamfara' },
];

export function stateLabel(value: string): string {
  return NIGERIAN_STATES.find((state) => state.value === value)?.label ?? value;
}
