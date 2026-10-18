// Leaflet maps for the Route and Shelters tabs (layers from GET /me/map).

import type { Feature, LineString, Point } from 'geojson';
import L from 'leaflet';
import type { LatLon, MapLayers, Shelter } from '../../lib/types.ts';

const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';
const DROP =
  '<svg class="drop" viewBox="0 0 26 36"><path d="M13 1C6.4 1 1 6.2 1 12.7 1 21.6 13 35 13 35s12-13.4 12-22.3C25 6.2 19.6 1 13 1Z"/><circle cx="13" cy="12.8" r="4.6"/></svg>';

const HOME_TIP: L.TooltipOptions = { direction: 'top', offset: [0, -10] };
const marker = (at: L.LatLngExpression, html: string, z = 0) =>
  L.marker(at, { icon: L.divIcon({ className: 'pin-wrap', html, iconSize: [0, 0] }), zIndexOffset: z });
const latlngs = (f: Feature) => (f.geometry as LineString).coordinates.map(([lon = 0, lat = 0]) => L.latLng(lat, lon));

/** A Harbor base map: Esri light gray, wheel and pinch zoom, our own zoom buttons. */
function baseMap(el: HTMLElement) {
  const map = L.map(el, { zoomControl: false, attributionControl: false, zoomSnap: 0.25, wheelPxPerZoomLevel: 90 });
  map.setView([27.95, -82.46], 7);
  L.tileLayer(`${ESRI}World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 16 }).addTo(map);
  L.tileLayer(`${ESRI}World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 16 }).addTo(map);
  const group = L.layerGroup().addTo(map);
  const resized = new ResizeObserver(() => map.invalidateSize()); // the card can grow after the map is made
  resized.observe(el);
  let home: L.LatLngBounds | null = null;
  const fit = (bounds = home) => {
    map.invalidateSize();
    if (bounds?.isValid()) map.fitBounds(bounds, { padding: [70, 70], maxZoom: 13 });
  };
  return {
    map,
    group,
    fit,
    setHome: (b: L.LatLngBounds) => {
      home = b;
    },
    zoomIn: () => map.zoomIn(0.75),
    zoomOut: () => map.zoomOut(0.75),
    remove: () => {
      resized.disconnect();
      map.remove();
    },
  };
}

/** The storm: cone and forecast track. */
function drawStorm(group: L.LayerGroup, layers: MapLayers) {
  L.geoJSON(layers.cone, { style: { className: 'cone' }, interactive: false }).addTo(group);
  L.geoJSON(layers.track, {
    style: { className: 'track' },
    interactive: false,
    filter: (f) => f.geometry.type === 'LineString',
  }).addTo(group);
}

/** One route line and its end point; returns its bounds. */
function drawOption(group: L.LayerGroup, f: Feature, on: boolean, click: () => void): L.LatLngBounds {
  const line = latlngs(f);
  L.polyline(line, { className: `route-outline${on ? ' on' : ''}` })
    .on('click', click)
    .addTo(group);
  L.polyline(line, { className: `route-core${on ? ' on' : ''}` })
    .on('click', click)
    .addTo(group);
  // No text label: the base map already names the city, so the name shows on hover
  const last = line.at(-1);
  if (last)
    marker(last, on ? DROP : '<span class="pin end"></span>', on ? 700 : 500)
      .bindTooltip(String(f.properties?.name ?? 'Destination'), { direction: 'top', offset: [0, on ? -36 : -8] })
      .on('click', click)
      .addTo(group);
  return L.latLngBounds(line);
}

/** Route: coral chosen route with a darker outline, sage alternates you can click, ink start dot, coral pin. */
export function routeMap(el: HTMLElement, onPick: (id: string) => void) {
  const m = baseMap(el);
  const draw = (layers: MapLayers, chosen: string | null) => {
    m.group.clearLayers();
    drawStorm(m.group, layers);
    const options = layers.route_options.features.length ? layers.route_options.features : layers.route.features;
    const id = (f: Feature) => String(f.properties?.id ?? chosen);
    const isOn = (f: Feature) => options.length === 1 || id(f) === chosen;
    let bounds: L.LatLngBounds | null = null;
    for (const f of [...options.filter((x) => !isOn(x)), ...options.filter(isOn)]) {
      const b = drawOption(m.group, f, isOn(f), () => !isOn(f) && onPick(id(f)));
      if (isOn(f)) bounds = b;
    }
    const home = layers.home.features[0]?.geometry as Point | undefined;
    if (home) {
      const [lon = 0, lat = 0] = home.coordinates;
      marker([lat, lon], '<span class="pin origin"></span>', 600).bindTooltip('Home', HOME_TIP).addTo(m.group);
      bounds = bounds ? bounds.extend([lat, lon]) : L.latLngBounds([[lat, lon]]);
    }
    if (bounds) m.setHome(bounds);
    m.fit();
  };
  return { ...m, draw };
}

/** Shelters: numbered pins, the selected one larger; clicking a pin picks it. */
export function shelterMap(el: HTMLElement, onPick: (i: number) => void) {
  const m = baseMap(el);
  let pins: L.Marker[] = [];
  const draw = (home: LatLon, shelters: Shelter[]) => {
    m.group.clearLayers();
    marker([home.lat, home.lon], '<span class="pin origin"></span>', 600).bindTooltip('Home', HOME_TIP).addTo(m.group);
    pins = shelters.map((s, i) =>
      marker([s.location.lat, s.location.lon], `<span class="pin count${i === 0 ? ' best' : ''}">${i + 1}</span>`, 500)
        .on('click', () => onPick(i))
        .addTo(m.group),
    );
    const bounds = L.latLngBounds([
      [home.lat, home.lon],
      ...shelters.map((s) => [s.location.lat, s.location.lon] as [number, number]),
    ]);
    m.setHome(bounds);
    m.fit();
  };
  const select = (i: number, fly = true) => {
    for (const [j, p] of pins.entries())
      p.getElement()
        ?.querySelector('.pin')
        ?.classList.toggle('on', i === j);
    const at = pins[i]?.getLatLng();
    if (at && fly) m.map.flyTo(at, Math.max(m.map.getZoom(), 12.5), { duration: 0.6 });
  };
  return { ...m, draw, select };
}
