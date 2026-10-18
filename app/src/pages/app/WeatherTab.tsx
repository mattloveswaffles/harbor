// Weather: the storm, its hazards at home and wind and rain over the coming days (GET /me/weather).
import { useEffect, useState } from 'react';
import { Icon } from '../../components/Icon.tsx';
import { api } from '../../lib/api.ts';
import { dudes } from '../../lib/assets.ts';
import { when } from '../../lib/format.ts';
import type { Weather } from '../../lib/types.ts';
import { Loading, Quiet } from './ui.tsx';
import { useDashboard } from './useHarbor.ts';

const LEVEL = { likely: 'Likely', possible: 'Possible', unlikely: 'Unlikely', watch: 'Watch in effect' } as const;
const band = (mph: number) => (mph >= 74 ? 'hu' : mph >= 39 ? 'ts' : 'calm');

/** Where an ISO time falls across the chart, as a percentage (null when outside it). */
function position(w: Weather, iso: string | null): number | null {
  const first = w.series[0];
  if (!iso || !first) return null;
  const start = Date.parse(first.at);
  const span = w.series.length * w.step_hours * 3_600_000;
  const x = ((Date.parse(iso) - start) / span) * 100;
  return x >= 0 && x <= 100 ? x : null;
}

const titleCase = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

function Storm({ w }: { w: Weather }) {
  const s = w.storm;
  const near = s?.category_at_closest ? `Category ${s.category_at_closest} as it passes` : 'Passes';
  return (
    <section className="banner storm-card">
      <img className="dude in-status" src={dudes.rumble} alt="" />
      <span className="grow">
        <strong>{s ? `${titleCase(s.classification)} ${s.name}` : 'No storm nearby'}</strong>
        <small>
          {s
            ? `${near} ${when(s.closest_at)}${s.closest_miles !== null ? ` · ${s.closest_miles} mi away` : ''}`
            : 'Harbor watches the National Hurricane Center for you.'}
        </small>
      </span>
      {s?.warning && (
        <span className="warning">
          <Icon name="alert" />
          {s.warning}
        </span>
      )}
    </section>
  );
}

function Hazards({ w }: { w: Weather }) {
  const h = w.hazards;
  return (
    <div className="hazards">
      <div className="hazard" style={{ '--tint': '#edf3ef' }}>
        <small>Wind</small>
        <strong>{h.wind.arrives_at ? when(h.wind.arrives_at) : `${h.wind.peak_gust_mph} mph`}</strong>
        <small>{h.wind.arrives_at ? `Storm winds arrive · gusts ${h.wind.peak_gust_mph} mph` : 'Peak gusts'}</small>
        <img className="dude in-hazard" src={dudes.gust} alt="" />
      </div>
      <div className="hazard" style={{ '--tint': '#e5eff1' }}>
        <small>Surge</small>
        <strong>Zone {h.surge.zone === 'unsure' ? '?' : h.surge.zone}</strong>
        <small>{h.surge.level === 'evacuate' ? 'Floods first: leave' : 'Low risk at home'}</small>
        <img className="dude in-hazard" src={dudes.plip} alt="" />
      </div>
      <div className="hazard" style={{ '--tint': '#eef2ec' }}>
        <small>Rain</small>
        <strong>{h.rain.total_in.toFixed(1)} in</strong>
        <small>Over the next {Math.round((w.series.length * w.step_hours) / 24)} days</small>
        <img className="dude in-hazard" src={dudes.nimbus} alt="" />
      </div>
      <div className="hazard also">
        <small>Also expect</small>
        <div className="also-row">
          <span className="ri">
            <Icon name="tornado" />
          </span>
          <span>
            <b>Tornadoes</b>
            <small>{LEVEL[h.tornado.level]}</small>
          </span>
        </div>
        <div className="also-row">
          <span className="ri">
            <Icon name="zap" />
          </span>
          <span>
            <b>Power outages</b>
            <small>{LEVEL[h.power.level]}</small>
          </span>
        </div>
      </div>
    </div>
  );
}

function Chart({ w }: { w: Weather }) {
  const top = Math.max(60, ...w.series.map((s) => s.gust_mph));
  const marks = [
    ['go', 'You leave', w.marks.leave_by],
    ['closest', 'Storm closest', w.marks.closest_at],
  ] as const;
  return (
    <section className="card conditions">
      <h2>
        At your home
        <span className="muted">
          Wind and gusts every {w.step_hours} hours · {w.source}
        </span>
        <span className="legend">
          <span>
            <i className="calm" />
            Under 39 mph
          </span>
          <span>
            <i className="ts" />
            Tropical storm
          </span>
          <span>
            <i className="hu" />
            Hurricane
          </span>
        </span>
      </h2>
      <div className="wx-chart" style={{ gridTemplateColumns: `repeat(${w.series.length}, 1fr)` }}>
        {marks.map(([cls, label, at]) => {
          const x = position(w, at);
          return (
            x !== null && (
              <span key={cls} className={`mark ${cls}`} style={{ left: `${x}%` }}>
                <b>{label}</b>
                {when(at)}
              </span>
            )
          );
        })}
        {w.series.map((s) => (
          <div key={s.at} className={`bar ${band(s.gust_mph)}`}>
            <span className="v">{s.gust_mph}</span>
            <i
              style={{ height: `${(s.gust_mph / top) * 100}%` }}
              title={`${s.wind_mph} mph wind, ${s.gust_mph} mph gusts`}
            />
            <small className="rain">{s.rain_in ? `${s.rain_in.toFixed(1)}″` : '–'}</small>
            <small className="t">{when(s.at)}</small>
          </div>
        ))}
      </div>
      <p className="foot">Bars are peak gusts in mph; rain is inches per {w.step_hours} hours.</p>
    </section>
  );
}

export default function WeatherTab() {
  const { data } = useDashboard();
  const [w, setW] = useState<Weather | null | undefined>(undefined);
  // Reload with the dashboard (the clock and storm move on)
  // biome-ignore lint/correctness/useExhaustiveDependencies: refetch when the storm status changes
  useEffect(() => {
    api.weather().then(setW, () => setW(null));
  }, [data.storm]);

  if (w === undefined) return <Loading />;
  if (w === null)
    return (
      <section className="tab">
        <div className="card">
          <Quiet icon="rain">The weather service didn't answer. Try again in a minute.</Quiet>
        </div>
      </section>
    );
  return (
    <section className="tab">
      <Storm w={w} />
      <Hazards w={w} />
      <Chart w={w} />
    </section>
  );
}
