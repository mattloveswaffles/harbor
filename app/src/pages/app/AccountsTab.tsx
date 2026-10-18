// Accounts: the evacuation fund, connected institutions (Nessie), the budget and the plan's money moves.
import { Icon } from '../../components/Icon.tsx';
import { api } from '../../lib/api.ts';
import { brands, dudes } from '../../lib/assets.ts';
import { money, moneyRound, when } from '../../lib/format.ts';
import type { Plan } from '../../lib/types.ts';
import { MOVE_STATUS, moveLabel, planStatus } from './labels.ts';
import { ActionButton, ApproveButton, Quiet } from './ui.tsx';
import { type HarborData, useDashboard } from './useHarbor.ts';

function Fund({ d }: { d: HarborData }) {
  const plan = d.plan;
  const parts = plan
    ? ([
        ['Checking', plan.sources.already_in_checking_cents, 'c1'],
        ['Savings', plan.sources.from_savings_cents, 'c2'],
        ['Investments', plan.sources.from_etf_sales_cents, 'c3'],
        ['Short', plan.shortfall_cents, 'c4'],
      ] as const)
    : [];
  const used = parts.filter(([, cents]) => cents > 0);
  const total = plan?.budget.total_cents ?? d.advice?.facts.trip_total_cents ?? 0;
  const [status, tone] = plan ? planStatus(plan) : [];
  return (
    <section className="card fund">
      <h2>
        Evacuation fund
        {plan && <span className={`tag ${tone}`}>{status}</span>}
      </h2>
      <div className="fund-big">
        <strong>{moneyRound(total)}</strong>
        <span>{plan ? `ready ${when(plan.cash_needed_by)}` : 'estimated trip cost'}</span>
      </div>
      {used.length > 0 && (
        <>
          <div className="stack" role="img" aria-label="Where the money comes from">
            {used.map(([label, cents, c]) => (
              <i key={label} className={c} style={{ flex: cents }} />
            ))}
          </div>
          <div className="legend">
            {used.map(([label, cents, c]) => (
              <span key={label}>
                <i className={c} />
                {label} {moneyRound(cents)}
              </span>
            ))}
          </div>
        </>
      )}
      {plan && plan.shortfall_cents > 0 && plan.help_resources.length > 0 && (
        <p className="help">
          <b>{moneyRound(plan.shortfall_cents)} short.</b>{' '}
          {plan.help_resources.map((h) => (
            <a key={h.label} href={h.url} target="_blank" rel="noopener">
              {h.label} {h.phone}
            </a>
          ))}
        </p>
      )}
      <div className="card-note">
        <img className="dude in-note" src={dudes.nimbus} alt="" />
        <span>
          <b>Spend it on anything.</b> Gas, a room, food. Unspent money goes back to savings after the storm.
        </span>
      </div>
    </section>
  );
}

function Connected({ d }: { d: HarborData }) {
  const { openSettings } = useDashboard();
  const linked = d.connections.filter((c) => c.connected);
  return (
    <section className="card">
      <h2>
        Connected
        <button className="link" type="button" onClick={() => openSettings('money')}>
          Manage
        </button>
      </h2>
      {linked.map((c) =>
        c.accounts
          .filter((a) => a.type !== 'brokerage_cash' || a.balance_cents > 0)
          .map((a) => (
            <div key={a.id} className="row">
              <span className="logo">
                <img src={brands[c.id as keyof typeof brands]} alt="" />
              </span>
              <span className="grow">
                <b>{a.nickname}</b>
                <small>{c.name}</small>
              </span>
              <strong>{money(a.balance_cents)}</strong>
            </div>
          )),
      )}
      {d.portfolio && linked.some((c) => c.kind === 'brokerage') && (
        <div className="row">
          <span className="logo">
            <img src={brands.robinhood} alt="" />
          </span>
          <span className="grow">
            <b>Investments</b>
            <small>{d.portfolio.holdings.map((h) => h.symbol).join(' · ')}</small>
          </span>
          <strong>{moneyRound(d.portfolio.total_value_cents)}</strong>
        </div>
      )}
      {!linked.length && <Quiet icon="bank">No accounts connected yet.</Quiet>}
      <button className="add" type="button" onClick={() => openSettings('money')}>
        <Icon name="plus" />
        Connect another account
      </button>
    </section>
  );
}

function Budget({ d }: { d: HarborData }) {
  const lines = d.plan?.budget.lines ?? d.advice?.facts.budget_lines ?? [];
  const top = Math.max(1, ...lines.map((l) => l.amount_cents));
  const total = lines.reduce((sum, l) => sum + l.amount_cents, 0);
  return (
    <section className="card">
      <h2>
        Budget <span className="muted">{moneyRound(total)}</span>
      </h2>
      <div className="budget">
        {lines.map((l) => (
          <div key={l.label} className="bline">
            <span>{l.label}</span>
            <i style={{ '--w': `${(l.amount_cents / top) * 100}%` }} />
            <strong>{moneyRound(l.amount_cents)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function Moves({ plan }: { plan: Plan }) {
  const moves = plan.moves.filter((m) => m.status !== 'cancelled' || plan.status === 'cancelled');
  return (
    <section className="card">
      <h2>Fund activity</h2>
      {moves.map((m) => {
        const [icon, label] = moveLabel(m);
        return (
          <div key={m.id} className="row move" data-status={m.status}>
            <span className="ri">
              <Icon name={icon} />
            </span>
            <span className="grow">
              <b>{label}</b>
              <small>
                {when(m.scheduled_for)}
                {m.error && ` · ${m.error.message}`}
              </small>
            </span>
            <strong>{money(m.amount_cents)}</strong>
            <span className="tag">{MOVE_STATUS[m.status]}</span>
          </div>
        );
      })}
      {plan.status === 'awaiting_approval' && <ApproveButton plan={plan} done="Plan approved." />}
      {['approved', 'running'].includes(plan.status) && (
        <ActionButton className="btn ghost" action={api.cancelPlan} done="Remaining steps cancelled.">
          Cancel remaining steps
        </ActionButton>
      )}
    </section>
  );
}

export default function AccountsTab() {
  const { data: d } = useDashboard();
  return (
    <section className="tab">
      <div className="cols wide-left">
        <Fund d={d} />
        <Connected d={d} />
      </div>
      <div className="cols">
        <Budget d={d} />
        {d.plan ? (
          <Moves plan={d.plan} />
        ) : (
          <section className="card">
            <h2>Fund activity</h2>
            <Quiet icon="shield">Harbor makes a money plan when a storm comes your way.</Quiet>
          </section>
        )}
      </div>
    </section>
  );
}
