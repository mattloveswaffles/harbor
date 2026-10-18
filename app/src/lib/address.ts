// Esri World Geocoder, called from the browser: suggestions, then the exact point.
export interface Place {
  label: string;
  zip: string;
  city: string;
  state: string;
  lat: number;
  lon: number;
}
export interface Suggestion {
  label: string;
  key: string;
}

const GEOCODER = 'https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer';
let near = ''; // "lon,lat" once the user shares their location: suggestions favour their area

/** Ask for the user's location once, to rank nearby addresses first. */
export function locateNearby(): void {
  if (near || !('geolocation' in navigator)) return;
  navigator.geolocation.getCurrentPosition(
    (p) => {
      near = `${p.coords.longitude},${p.coords.latitude}`;
    },
    () => undefined,
    { maximumAge: 600_000, timeout: 8000 },
  );
}

async function getJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url);
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

/** "2301 Bayshore Blvd, Tampa, FL, 33629, USA" -> "2301 Bayshore Blvd, Tampa, FL 33629" */
export const tidy = (text: string): string => text.replace(/, USA$/, '').replace(/, ([A-Z]{2}), (\d{5})$/, ', $1 $2');

export async function suggest(text: string): Promise<Suggestion[]> {
  if (text.trim().length < 3) return [];
  const params = new URLSearchParams({
    text,
    f: 'json',
    maxSuggestions: '5',
    countryCode: 'USA',
    category: 'Address,Postal',
    ...(near ? { location: near } : {}),
  });
  const body = await getJson<{ suggestions?: { text: string; magicKey: string }[] }>(`${GEOCODER}/suggest?${params}`);
  return (body?.suggestions ?? []).map((s) => ({ label: tidy(s.text), key: s.magicKey }));
}

export async function resolvePlace(s: Suggestion): Promise<Place | null> {
  const params = new URLSearchParams({
    SingleLine: s.label,
    magicKey: s.key,
    f: 'json',
    maxLocations: '1',
    outFields: 'StAddr,City,RegionAbbr,Postal',
  });
  type Candidate = {
    location: { x: number; y: number };
    attributes: { StAddr: string; City: string; RegionAbbr: string; Postal: string };
  };
  const body = await getJson<{ candidates?: Candidate[] }>(`${GEOCODER}/findAddressCandidates?${params}`);
  const c = body?.candidates?.[0];
  if (!c?.attributes.Postal) return null;
  const a = c.attributes;
  return {
    label: [a.StAddr, a.City, `${a.RegionAbbr} ${a.Postal}`].filter((x) => x.trim()).join(', '),
    zip: a.Postal,
    city: a.City,
    state: a.RegionAbbr,
    lat: c.location.y,
    lon: c.location.x,
  };
}

export async function firstPlace(text: string): Promise<Place | null> {
  const [first] = await suggest(text);
  return first ? resolvePlace(first) : null;
}
