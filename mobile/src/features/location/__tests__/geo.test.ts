import {
  describeDistance,
  distanceMetres,
  formatDistance,
  regionFor,
  toCoordinate,
} from '@/features/location/geo';

// Victoria Island and Ikeja, both real and about 17km apart.
const VI = { latitude: 6.428055, longitude: 3.421944 };
const IKEJA = { latitude: 6.6018, longitude: 3.3515 };

describe('reading coordinates off the API', () => {
  it('parses the decimal strings the API sends', () => {
    // Decimals cross the wire as strings because a float is not a safe carrier
    // for a fixed-precision column.
    expect(toCoordinate('6.428055', '3.421944')).toEqual(VI);
  });

  it('accepts numbers too, for coordinates that came from the device', () => {
    expect(toCoordinate(6.428055, 3.421944)).toEqual(VI);
  });

  it('treats an unpinned address as having no location', () => {
    expect(toCoordinate(null, null)).toBeNull();
    expect(toCoordinate(undefined, undefined)).toBeNull();
  });

  it('refuses a half-set pair', () => {
    // The API validates these as a pair, so half of one means the row is wrong.
    expect(toCoordinate('6.428055', null)).toBeNull();
    expect(toCoordinate(null, '3.421944')).toBeNull();
  });

  it('refuses null island', () => {
    // 0,0 is a real coordinate in the Gulf of Guinea, about 600km from Lagos,
    // which makes it exactly the plausible-looking wrong answer an unset pair
    // produces. Nothing Sync serves is there.
    expect(toCoordinate(0, 0)).toBeNull();
  });

  it('refuses values off the globe', () => {
    expect(toCoordinate(91, 0)).toBeNull();
    expect(toCoordinate(0, 181)).toBeNull();
  });

  it('refuses text that is not a number', () => {
    expect(toCoordinate('somewhere', 'else')).toBeNull();
    expect(toCoordinate('', '')).toBeNull();
  });
});

describe('distance', () => {
  it('measures a known Lagos distance', () => {
    const metres = distanceMetres(VI, IKEJA);

    // Straight line VI to Ikeja is about 20km. Loose bounds, because the point
    // is that the maths is right, not that it matches one reference to a metre.
    expect(metres).toBeGreaterThan(18_000);
    expect(metres).toBeLessThan(22_000);
  });

  it('is zero for the same point', () => {
    expect(distanceMetres(VI, VI)).toBeCloseTo(0, 5);
  });

  it('is symmetric', () => {
    expect(distanceMetres(VI, IKEJA)).toBeCloseTo(distanceMetres(IKEJA, VI), 6);
  });
});

describe('formatting distance', () => {
  it('rounds to fifty metres below a kilometre', () => {
    // A phone's fix is rarely better than this, so more precision is a lie.
    expect(formatDistance(637)).toBe('650 m');
    expect(formatDistance(120)).toBe('100 m');
  });

  it('never claims better than fifty metres', () => {
    expect(formatDistance(3)).toBe('50 m');
    expect(formatDistance(0)).toBe('50 m');
  });

  it('uses one decimal place in the single kilometres', () => {
    expect(formatDistance(4_230)).toBe('4.2 km');
    expect(formatDistance(1_000)).toBe('1.0 km');
  });

  it('drops the decimal once it stops being meaningful', () => {
    expect(formatDistance(17_400)).toBe('17 km');
    expect(formatDistance(120_000)).toBe('120 km');
  });

  it('says nothing rather than something wrong', () => {
    expect(formatDistance(Number.NaN)).toBe('');
    expect(formatDistance(-5)).toBe('');
  });
});

describe('describing distance for a screen reader', () => {
  it('spells out the unit', () => {
    expect(describeDistance(4_230)).toBe('Approximately 4.2 kilometres away');
    expect(describeDistance(650)).toBe('Approximately 650 metres away');
  });

  it('is marked as approximate', () => {
    expect(describeDistance(4_230)).toMatch(/^Approximately/);
  });
});

describe('the camera region', () => {
  it('centres on a single point', () => {
    const region = regionFor([VI]);

    expect(region?.latitude).toBeCloseTo(VI.latitude, 6);
    expect(region?.longitude).toBeCloseTo(VI.longitude, 6);
  });

  it('does not zoom to the maximum for one point', () => {
    // A single marker at full zoom looks like the map is broken.
    const region = regionFor([VI]);

    expect(region!.latitudeDelta).toBeGreaterThan(0.01);
  });

  it('contains both points with room to spare', () => {
    const region = regionFor([VI, IKEJA])!;
    const spanLat = Math.abs(VI.latitude - IKEJA.latitude);

    expect(region.latitudeDelta).toBeGreaterThan(spanLat);
    expect(region.latitude).toBeCloseTo((VI.latitude + IKEJA.latitude) / 2, 6);
  });

  it('has nothing to show for no points', () => {
    expect(regionFor([])).toBeNull();
  });
});
