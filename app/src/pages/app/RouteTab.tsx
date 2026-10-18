// Route: the map, when to leave, where to go and what's on the way.
import { useEffect, useRef, useState } from 'react';
import { Icon } from '../../components/Icon.tsx';
import { api } from '../../lib/api.ts';
import { brands, dudes } from '../../lib/assets.ts';
import { duration, moneyRound, when } from '../../lib/format.ts';
import type { Atm } from '../../lib/types.ts';
import { routeMap } from './harborMap.ts';
import { Quiet, ZoomButtons } from './ui.tsx';
import { useDashboard } from './useHarbor.ts';

export default function RouteTab() {
  const { data, act } = useDashboard();
  const { guide } = data;
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<ReturnType<typeof routeMap>>(null);
  const [atms, setAtms] = useState<Atm[]>([]);
  const choose = (id: string) => act(() => api.chooseDestination(id), 'Destination updated.');

  // biome-ignore lint/correctness/useExhaustiveDependencies: the map is made once; `choose` only needs `act`
  useEffect(() => {
    if (!el.current) return;
    map.current = routeMap(el.current, choose);
    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => map.current?.draw(data.map.layers, guide?.chosen ?? null), [data.map, guide?.chosen]);
  useEffect(() => {
    if (guide) api.atms().then(setAtms, () => undefined);
  }, [guide]);

  const chosen = guide?.destinations.find((d) => d.id === guide.chosen);
  const r = guide?.route;
  const range = data.advice?.facts.range_mi ?? null;
  const atm = atms.find((a) => !a.in_forecast_cone) ?? atms[0];
  return (
    <section className="tab">
      <div className="cols map-left">
        <section className="card map">
          <div className="map-host" ref={el} />
          {r && chosen && (
            <div className="map-badge">
              <b>{duration(r.drive_time_min_evac)}</b>
              <small>
                to {chosen.name} · {Math.round(r.distance_mi)} mi
              </small>
            </div>
          )}
          <div className="map-legend">
            <span>
              <i className="l-route" />
              Your route
            </span>
            <span>
              <i className="l-cone" />
              Forecast cone
            </span>
          </div>
          <ZoomButtons map={map} />
        </section>
        <div className="stack-col">
          <section className="banner leave" data-tone="alert">
            <img className="dude in-status" src={dudes.foggy} alt="" />
            <span className="grow">
              <strong>{guide?.leave_by ? `Leave by ${when(guide.leave_by)}` : 'No need to leave yet'}</strong>
              <small>{r?.corridor ?? r?.drive_time_note ?? 'Harbor tells you when it is time.'}</small>
            </span>
          </section>
          <section className="card">
            <h2>Where to go</h2>
            {guide?.destinations.length ? (
              guide.destinations.slice(0, 4).map((d) => (
                <button
                  key={d.id}
                  type="button"
                  className={d.id === guide.chosen ? 'dest on' : 'dest'}
                  onClick={() => d.id !== guide.chosen && choose(d.id)}
                >
                  <span className="grow">
                    <b>{d.name}</b>
                    <small>{d.outside_cone ? 'Outside the cone' : 'In the cone'}</small>
                  </span>
                  {d.recommended && <span className="tag on">Best</span>}
                  {!d.outside_cone && <span className="tag warn">Risky</span>}
                  <strong>{duration(d.drive_time_min_evac)}</strong>
                </button>
              ))
            ) : (
              <Quiet icon="route">Destinations appear when a storm comes your way.</Quiet>
            )}
          </section>
          <section className="card">
            <h2>On the way</h2>
            {range !== null && r && (
              <div className="stop">
                <Icon name="fuel" />
                <span className="grow">
                  <b>{range < r.distance_mi ? 'Fill up before you go' : 'Top up the tank'}</b>
                  <small>
                    {range} mi in the tank · {Math.round(r.distance_mi)} mi to drive
                  </small>
                </span>
              </div>
            )}
            {atm && (
              <div className="stop">
                <Icon name="money" />
                <span className="grow">
                  <b>Cash: {atm.name}</b>
                  <small>
                    {Math.round(atm.distance_miles)} mi · {atm.on_evacuation_route ? 'on your route' : 'near home'}
                    {atm.in_forecast_cone ? ' · in the cone' : ''}
                  </small>
                </span>
              </div>
            )}
            {guide?.lodging && (
              <div className="stop">
                <Icon name="hotel" />
                <span className="grow">
                  <b>{guide.lodging.options[0]?.name ?? 'A room'}</b>
                  <small>
                    {guide.lodging.nights} nights · about {moneyRound(guide.lodging.nightly_estimate_cents)} a night
                  </small>
                </span>
              </div>
            )}
            {r && (
              <div className="btn-row">
                <a className="btn ghost map-app" href={r.links.google} target="_blank" rel="noopener">
                  <img src={brands.googlemaps} alt="" />
                  Google Maps
                  <Icon name="external" />
                </a>
                <a className="btn ghost map-app" href={r.links.apple} target="_blank" rel="noopener">
                  <img src={brands.applemaps} alt="" />
                  Apple Maps
                  <Icon name="external" />
                </a>
              </div>
            )}
          </section>
        </div>
      </div>
    </section>
  );
}
