// My plan: when to leave, then the whole plan as one journey (get ready, leave, arrive) against the storm.
import { Link } from 'react-router';
import { Icon, type IconName } from '../../components/Icon.tsx';
import { api } from '../../lib/api.ts';
import { dudes } from '../../lib/assets.ts';
import { duration, moneyRound, pct, when } from '../../lib/format.ts';
import type { AdviceStep } from '../../lib/types.ts';
import { Line, Phase, Track } from './journey.tsx';
import { ActionButton } from './ui.tsx';
import { type HarborData, useDashboard } from './useHarbor.ts';

function headline({ storm, guide }: HarborData): string {
  if (storm.risk_level === 'shelter') return 'Stay sheltered';
  if (storm.risk_level === 'recover') return 'The storm has passed';
  if (!storm.storm) return 'All clear';
  return guide?.leave_by ? `Leave by ${when(guide.leave_by)}` : 'Get ready';
}

function subline({ storm }: HarborData): string {
  const s = storm.storm;
  if (!s)
    return storm.risk_level === 'recover' ? 'Harbor is putting your money back.' : 'No storm threatens your home.';
  const zip = storm.at_your_zip;
  const winds = zip.earliest_ts_winds_eta ? ` · storm winds ${when(zip.earliest_ts_winds_eta)}` : '';
  return `${s.name} · ${pct(zip.ts_wind_probability_5day)} chance of storm winds at home${winds}`;
}

function Banner({ d }: { d: HarborData }) {
  const tone = !d.storm.storm ? 'calm' : ['act', 'shelter'].includes(d.storm.risk_level) ? 'alert' : 'watch';
  const plan = d.plan;
  return (
    <section className="banner" data-tone={tone}>
      <img className="dude in-status" src={dudes.squall} alt="" />
      <span className="grow">
        <strong>{headline(d)}</strong>
        <small>{subline(d)}</small>
      </span>
      {d.guide?.route && (
        <Link className="btn ghost" to="route">
          View route
        </Link>
      )}
      {plan?.status === 'awaiting_approval' && (
        <ActionButton
          className="btn"
          action={() => api.approve(plan.version)}
          done="Plan approved. Harbor is moving your money."
        >
          Approve {moneyRound(plan.budget.total_cents)}
          <Icon name="arrow" />
        </ActionButton>
      )}
    </section>
  );
}

const PREP_ICON: Partial<Record<AdviceStep['kind'], IconName>> = {
  medicine: 'pill',
  car: 'fuel',
  pet: 'heart',
  packing: 'check',
  shelter: 'tent',
};

function GetReady({ d }: { d: HarborData }) {
  const facts = d.advice?.facts;
  const prep = (d.advice?.advice?.steps ?? []).filter((s) => s.kind !== 'money');
  const total = d.plan?.budget.total_cents ?? facts?.trip_total_cents ?? 0;
  const ready = d.plan ? ` · ready ${when(d.plan.cash_needed_by)}` : '';
  return (
    <Phase label="Get ready" value="Now" dude={dudes.zip}>
      <Line icon="wallet">
        {facts?.connected.length ? `${moneyRound(total)} fund${ready}` : 'Connect a bank to fund the trip'}
      </Line>
      {prep.slice(0, 3).map((s) => (
        <Line key={s.title} icon={PREP_ICON[s.kind] ?? 'check'}>
          {s.title}
        </Line>
      ))}
    </Phase>
  );
}

function Leave({ d }: { d: HarborData }) {
  const route = d.guide?.route;
  const range = d.advice?.facts.range_mi;
  return (
    <Phase label="Leave" value={d.guide?.leave_by ? when(d.guide.leave_by) : 'Not yet'} dude={dudes.twirl}>
      {route ? (
        <>
          <Line icon="route">{route.corridor ?? 'Fastest route'}</Line>
          <Line icon="clock">{duration(route.drive_time_min_evac)} in evacuation traffic</Line>
          {range != null && (
            <Line icon="fuel">
              {range} mi in the tank · {Math.round(route.distance_mi)} mi to drive
            </Line>
          )}
        </>
      ) : (
        <Line icon="alert">Harbor tells you when it’s time</Line>
      )}
    </Phase>
  );
}

function Arrive({ d }: { d: HarborData }) {
  const guide = d.guide;
  const advice = d.advice?.advice;
  const dest = guide?.destinations.find((x) => x.id === (advice?.destination_id ?? guide.chosen));
  const leave = guide?.leave_by;
  const arrive = leave && guide?.route ? Date.parse(leave) + guide.route.drive_time_min_evac * 60_000 : null;
  const stay = guide?.lodging?.options[0];
  const shelter = guide?.shelters.find((s) => s.id === advice?.shelter_id) ?? guide?.shelters[0];
  return (
    <Phase label="Arrive" value={dest?.name ?? 'A safe place'}>
      {arrive && <Line icon="clock">Around {when(new Date(arrive).toISOString())}</Line>}
      {stay && guide?.lodging && (
        <Line icon="hotel">
          {stay.name} · {guide.lodging.nights} nights
        </Line>
      )}
      {shelter && (
        <Line icon="tent">
          Backup: {shelter.name}
          {shelter.pets === 'yes' ? ' · pets ok' : ''}
        </Line>
      )}
    </Phase>
  );
}

function Journey({ d }: { d: HarborData }) {
  const advice = d.advice;
  const storm = advice?.facts.storm_winds_at ?? d.storm.at_your_zip.earliest_ts_winds_eta;
  return (
    <section className="card journey">
      <header className="journey-head">
        <span className="grow">
          <h2>Your plan</h2>
          {advice?.advice ? (
            <p>{advice.advice.summary}</p>
          ) : (
            <p className={advice?.status === 'error' ? undefined : 'shimmer'}>
              {advice?.error ?? 'Harbor is writing your plan…'}
            </p>
          )}
        </span>
        <ActionButton className="btn ghost small" action={api.regenerate} done="Harbor is rethinking your plan.">
          <Icon name="refresh" />
          Regenerate
        </ActionButton>
      </header>
      <Track
        end={
          storm && (
            <span className="track-end alert">
              <Icon name="rain" />
              Storm winds {when(storm)}
            </span>
          )
        }
      />
      <div className="phases">
        <GetReady d={d} />
        <Leave d={d} />
        <Arrive d={d} />
      </div>
    </section>
  );
}

export default function PlanTab() {
  const { data: d } = useDashboard();
  return (
    <section className="tab plan-tab">
      <Banner d={d} />
      <Journey d={d} />
    </section>
  );
}
