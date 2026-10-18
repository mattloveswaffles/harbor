// A reply's work, above the answer: while it runs, a line per step as it streams, the newest glowing; once the
// answer begins, one line, "Thought for 9s", that opens to all of them. A thought opens to its reasoning.
import { Fragment, useState } from 'react';
import { Icon, type IconName } from '../../components/Icon.tsx';

/** A step of the reply: the model thinking, or a lookup. */
export type Step = { thinking: string } | { tool: string };

/** What each tool looks at ("Checked your route", "Checking your route") and its icon. */
const SOURCES: Record<string, [string, IconName]> = {
  household: ['home', 'home'],
  household_details: ['household', 'group'],
  storm_status: ['storm', 'rain'],
  weather_at_home: ['weather', 'rain'],
  bank_accounts: ['bank', 'bank'],
  connected_accounts: ['accounts', 'bank'],
  investments: ['investments', 'chart'],
  evacuation_plan: ['plan', 'shield'],
  evacuation_guide: ['route', 'route'],
  evacuation_advice: ['advice', 'shield'],
  regenerate_advice: ['advice', 'refresh'],
  bills: ['bills', 'calendar'],
  nearby_atms: ['ATMs', 'money'],
  nearby_sensors: ['sensors', 'activity'],
};

interface Line {
  key: string;
  icon: IconName;
  done: string;
  doing: string;
  reasoning?: string;
  running: boolean;
}

/** A thought's sections, as reasoning comes: `**Heading**`, then what it says. */
function sections(thinking: string): { heading: string; body: string }[] {
  const parts = thinking.split(/\*\*([^*\n]+)\*\*/);
  const said = parts[0]?.trim() ? [{ heading: '', body: parts[0].trim() }] : [];
  for (let at = 1; at < parts.length; at += 2) {
    said.push({ heading: parts[at]?.trim() ?? '', body: parts[at + 1]?.trim() ?? '' });
  }
  return said;
}

/** The steps as lines; while `live`, the last one is still running. Lookups of one tool in a row are one line. */
function lines(steps: Step[], live: boolean): Line[] {
  const said: Line[] = [];
  for (const [index, step] of steps.entries()) {
    const last = live && index === steps.length - 1;
    if ('thinking' in step) {
      const parts = sections(step.thinking);
      for (const [n, { heading, body }] of parts.entries()) {
        said.push({
          key: `${index}.${n}`,
          icon: 'thought',
          done: heading || 'Thought',
          doing: heading || 'Thinking',
          reasoning: body || undefined,
          running: last && n === parts.length - 1,
        });
      }
      continue;
    }
    const before = steps[index - 1];
    const line = said.at(-1);
    if (line && before && 'tool' in before && before.tool === step.tool) {
      line.running = last;
      continue;
    }
    const [what, icon] = SOURCES[step.tool] ?? ['data', 'check'];
    said.push({ key: `${index}`, icon, done: `Checked your ${what}`, doing: `Checking your ${what}`, running: last });
  }
  return said;
}

const took = (seconds: number) =>
  seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m${seconds % 60 ? ` ${seconds % 60}s` : ''}`;

export function Work({ steps, working, seconds }: { steps: Step[]; working: boolean; seconds?: number }) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState<string[]>([]);
  const all = lines(steps, working);
  const toggle = (key: string) => setShown((s) => (s.includes(key) ? s.filter((k) => k !== key) : [...s, key]));

  const list = (
    <div className="work-lines">
      {all.map((line) => {
        const detailed = !line.running && Boolean(line.reasoning);
        const row = (
          <>
            <Icon name={line.icon} />
            <span className={line.running ? 'work-text glow' : 'work-text'}>
              {line.running ? line.doing : line.done}
            </span>
            {detailed && <Icon name="chevron" className="chev" />}
          </>
        );
        if (!detailed)
          return (
            <div key={line.key} className="work-line">
              {row}
            </div>
          );
        const isOpen = shown.includes(line.key);
        return (
          <Fragment key={line.key}>
            <button
              type="button"
              className={isOpen ? 'work-line open' : 'work-line'}
              aria-expanded={isOpen}
              onClick={() => toggle(line.key)}
            >
              {row}
            </button>
            {isOpen && <div className="work-detail">{line.reasoning}</div>}
          </Fragment>
        );
      })}
    </div>
  );

  if (working)
    return (
      <div className="work">
        {all.length ? (
          list
        ) : (
          <div className="work-line">
            <Icon name="thought" />
            <span className="work-text glow">Thinking</span>
          </div>
        )}
      </div>
    );
  if (!all.length) return null;
  return (
    <div className="work">
      <button
        type="button"
        className={open ? 'work-summary open' : 'work-summary'}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {seconds ? `Thought for ${took(seconds)}` : 'Thought'}
        <Icon name="chevron" className="chev" />
      </button>
      {open && list}
    </div>
  );
}
