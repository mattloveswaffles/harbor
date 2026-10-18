import { type ReactNode, type RefObject, useEffect, useRef, useState } from 'react';
import { Icon, type IconName } from '../../components/Icon.tsx';
import { api } from '../../lib/api.ts';
import { mark } from '../../lib/assets.ts';
import { moneyRound } from '../../lib/format.ts';
import type { Plan } from '../../lib/types.ts';
import { useDashboard } from './useHarbor.ts';

/** Harbor's loading screen: the mark and a spinner, centred on the page or in the tab. */
export function Loading({ page, children }: { page?: boolean; children?: ReactNode }) {
  return (
    <div className={page ? 'boot' : 'boot in-tab'}>
      <img src={mark} alt="" />
      {children ?? <span className="spin" />}
    </div>
  );
}

/** A button that runs a server action, shows it's busy, then reloads and confirms. */
export function ActionButton({
  action,
  done,
  className,
  children,
}: {
  action: () => Promise<unknown>;
  done: string;
  className: string;
  children: ReactNode;
}) {
  const { act } = useDashboard();
  const [busy, setBusy] = useState(false);
  return (
    <button
      className={busy ? `${className} busy` : className}
      type="button"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        await act(action, done);
        setBusy(false);
      }}
    >
      {children}
    </button>
  );
}

export function ApproveButton({ plan, done }: { plan: Plan; done: string }) {
  return (
    <ActionButton className="btn" action={() => api.approve(plan.version)} done={done}>
      Approve {moneyRound(plan.budget.total_cents)}
      <Icon name="arrow" />
    </ActionButton>
  );
}

export function Quiet({ icon, children }: { icon: IconName; children: ReactNode }) {
  return (
    <p className="quiet">
      <Icon name={icon} />
      {children}
    </p>
  );
}

/** A map made once on `el` and removed on unmount. */
export function useMap<M extends { remove(): void }>(make: (el: HTMLElement) => M) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<M>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: the map is made once
  useEffect(() => {
    if (!el.current) return;
    map.current = make(el.current);
    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, []);
  return { el, map };
}

/** + / − / recenter over a map. */
export function ZoomButtons({ map }: { map: RefObject<{ zoomIn(): void; zoomOut(): void; fit(): void } | null> }) {
  return (
    <div className="map-zoom">
      <button type="button" aria-label="Zoom in" onClick={() => map.current?.zoomIn()}>
        +
      </button>
      <button type="button" aria-label="Zoom out" onClick={() => map.current?.zoomOut()}>
        −
      </button>
      <button type="button" aria-label="Recenter" onClick={() => map.current?.fit()}>
        <Icon name="location" />
      </button>
    </div>
  );
}
