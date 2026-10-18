// Shelters: the best match for the household, the list and a map whose pins follow the list.
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Icon } from '../../components/Icon.tsx';
import { dudes } from '../../lib/assets.ts';
import type { Shelter } from '../../lib/types.ts';
import { shelterMap } from './harborMap.ts';
import { Quiet, useMap, ZoomButtons } from './ui.tsx';
import { useDashboard } from './useHarbor.ts';

const FILTERS = {
  pets: ['Pets welcome', (s: Shelter) => s.pets !== 'no'],
  access: ['Accessible', (s: Shelter) => s.ada !== 'no' && s.wheelchair !== 'no'],
  space: ['Has space', (s: Shelter) => s.status === 'open'],
} as const;
type Filter = keyof typeof FILTERS;

const where = (s: Shelter) =>
  [s.address, s.city, [s.state, s.zip].filter(Boolean).join(' ')].filter(Boolean).join(', ');
const spaces = (s: Shelter) =>
  s.capacity != null && s.population != null
    ? `${Math.max(0, s.capacity - s.population)} of ${s.capacity} spaces left`
    : null;

function Best({ s, pets }: { s: Shelter; pets: boolean }) {
  return (
    <section className="banner good">
      <img className="dude in-status" src={dudes.flurry} alt="" />
      <span className="grow">
        <small className="eyebrow">Best for you</small>
        <strong>{s.name}</strong>
        <small>
          {s.distance_mi.toFixed(1)} mi · {where(s) || 'Address on arrival'} · bring ID, meds, bedding
          {pets ? ' and a crate' : ''}
        </small>
      </span>
      <a className="btn" href={s.links.google} target="_blank" rel="noopener">
        Directions
        <Icon name="arrow" />
      </a>
    </section>
  );
}

/** One FEMA record: where it is, whether it's open, who runs it and who it takes. */
function ShelterRow({ s, i, on, onPick }: { s: Shelter; i: number; on: boolean; onPick: () => void }) {
  const facts = [
    s.org && `Run by ${s.org}`,
    s.hours,
    spaces(s),
    s.pets === 'yes' ? 'Pets welcome' : s.pets === 'no' && 'No pets',
    (s.ada === 'yes' || s.wheelchair === 'yes') && 'Wheelchair accessible',
    s.kind === 'special_needs' && 'Special needs',
  ].filter(Boolean);
  return (
    <button type="button" className={on ? 'srow on' : 'srow'} onClick={onPick}>
      <span className={i === 0 ? 'num-badge best' : 'num-badge'}>{i + 1}</span>
      <span className="grow">
        <b>{s.name}</b>
        <small>{where(s) || 'Address on arrival'}</small>
        <small className="sfacts">{facts.join(' · ')}</small>
      </span>
      <span className="cap">
        <b>{s.distance_mi.toFixed(1)} mi</b>
        <small className={s.status === 'open' ? 'ok' : 'full'}>{s.status === 'open' ? 'Open' : 'Full'}</small>
      </span>
    </button>
  );
}

function ShelterList({ all }: { all: Shelter[] }) {
  const { data } = useDashboard();
  const [on, setOn] = useState<Filter[]>(data.user.household.pets.length ? ['pets'] : []);
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState(0);
  const q = query.trim().toLowerCase();
  const shelters = all.filter(
    (s) => on.every((f) => FILTERS[f][1](s)) && (!q || `${s.name} ${where(s)}`.toLowerCase().includes(q)),
  );
  const { el, map } = useMap((host) => shelterMap(host, (i) => pick(i)));
  // biome-ignore lint/correctness/useExhaustiveDependencies: redraw when the filtered list changes
  useEffect(() => {
    map.current?.draw(data.user.location, shelters);
    map.current?.select(0, false);
    setPicked(0);
  }, [data.user.location, shelters.map((s) => s.id).join()]);
  const pick = (i: number) => {
    setPicked(i);
    map.current?.select(i);
  };

  return (
    <>
      {all[0] && <Best s={all[0]} pets={data.user.household.pets.length > 0} />}
      <div className="filters">
        <label className="quick-ask">
          <Icon name="search" />
          <input
            type="search"
            value={query}
            placeholder="Search shelters, streets or cities"
            aria-label="Search shelters"
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {(Object.keys(FILTERS) as Filter[]).map((f) => (
          <button
            key={f}
            type="button"
            className="chip"
            aria-pressed={on.includes(f)}
            onClick={() => setOn((x) => (x.includes(f) ? x.filter((y) => y !== f) : [...x, f]))}
          >
            {FILTERS[f][0]}
          </button>
        ))}
        <span className="muted">{all[0]?.source}</span>
      </div>
      <div className="cols shelter-grid">
        <section className="card slist">
          {shelters.length ? (
            shelters.map((s, i) => <ShelterRow key={s.id} s={s} i={i} on={i === picked} onPick={() => pick(i)} />)
          ) : (
            <Quiet icon="tent">No shelter matches.</Quiet>
          )}
        </section>
        <section className="card map">
          <div className="map-host" ref={el} />
          <ZoomButtons map={map} />
        </section>
      </div>
    </>
  );
}

function NoShelters({ pets }: { pets: boolean }) {
  return (
    <section className="card empty">
      <img className="dude in-empty" src={dudes.flurry} alt="" />
      <span className="grow">
        <h2>No shelters open yet</h2>
        <p>
          When a storm heads your way, Harbor lists the open shelters near you that fit your family
          {pets ? ' and take your pets' : ''}.
        </p>
        <Link className="btn ghost" to="/app/weather">
          Check the weather
          <Icon name="arrow" />
        </Link>
      </span>
    </section>
  );
}

export default function SheltersTab() {
  const { data } = useDashboard();
  const all = data.guide?.shelters ?? [];
  return (
    <section className="tab">
      {all.length ? <ShelterList all={all} /> : <NoShelters pets={data.user.household.pets.length > 0} />}
    </section>
  );
}
