// One card, three phases on a numbered track: the layout of My plan and Accounts.
import type { ReactNode } from 'react';
import { Icon, type IconName } from '../../components/Icon.tsx';

/** 1 → 2 → 3, with an optional marker (a deadline or "ready") at the end. */
export function Track({ end }: { end?: ReactNode }) {
  return (
    <ol className="plan-track" aria-hidden="true">
      <li>
        <b>1</b>
      </li>
      <li>
        <b>2</b>
      </li>
      <li>
        <b>3</b>
        {end}
      </li>
    </ol>
  );
}

export function Phase({
  label,
  value,
  children,
  dude,
}: {
  label: string;
  value: string;
  children: ReactNode;
  dude?: string;
}) {
  return (
    <div className="phase">
      <small className="phase-label">{label}</small>
      <strong className="phase-value">{value}</strong>
      <ul className="phase-list">{children}</ul>
      {dude && <img className="dude in-phase" src={dude} alt="" />}
    </div>
  );
}

/** A line in a phase: an icon and the text. */
export function Line({ icon, children }: { icon: IconName; children: ReactNode }) {
  return (
    <li>
      <Icon name={icon} />
      <span className="grow">{children}</span>
    </li>
  );
}
