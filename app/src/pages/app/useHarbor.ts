// Dashboard data: loaded together, reloaded on every live event.
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { ApiError, api } from '../../lib/api.ts';
import type {
  Advice,
  Connection,
  Guide,
  MapOut,
  Plan,
  Portfolio,
  StormStatus,
  User,
  ZipInfo,
} from '../../lib/types.ts';
import { TOAST_EVENTS } from './labels.ts';
import { useToast } from './toast.tsx';

export interface HarborData {
  user: User;
  place: ZipInfo | null;
  storm: StormStatus;
  portfolio: Portfolio | null;
  plan: Plan | null;
  guide: Guide | null;
  map: MapOut;
  advice: Advice | null;
  connections: Connection[];
}

export type SettingsTab = 'you' | 'places' | 'household' | 'medical' | 'vehicle' | 'money' | 'alerts' | 'privacy';

export interface Dashboard {
  data: HarborData;
  /** Run an action, reload, and confirm with a toast (errors become a toast too). */
  act: (action: () => Promise<unknown>, done: string) => Promise<void>;
  /** Open the Settings popup on a tab. */
  openSettings: (tab?: SettingsTab) => void;
}

export const DashboardContext = createContext<Dashboard | null>(null);

export function useDashboard(): Dashboard {
  const value = useContext(DashboardContext);
  if (!value) throw new Error('useDashboard needs a DashboardContext');
  return value;
}

/** Optional sections fail quietly, but an expired login still signs the user out. */
async function optional<T>(p: Promise<T>): Promise<T | null> {
  try {
    return await p;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) throw err;
    return null;
  }
}

async function loadAll(): Promise<HarborData> {
  const [user, storm, portfolio, plan, guide, map, advice, connections] = await Promise.all([
    api.me(),
    api.storm(),
    optional(api.portfolio()),
    api.plan(),
    api.evacuation(),
    api.map(),
    optional(api.advice()),
    optional(api.connections()),
    optional(api.accounts()), // refreshes the Nessie balances the connections show
  ]);
  const place = await optional(api.zip(user.zip));
  return { user, place, storm, portfolio, plan, guide, map, advice, connections: connections ?? [] };
}

/** `onSignedOut` must be stable (useCallback): it's a dependency of the live connection. */
export function useHarbor(onSignedOut: () => void) {
  const toast = useToast();
  const [data, setData] = useState<HarborData | null>(null);

  const reload = useCallback(async () => {
    try {
      setData(await loadAll());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onSignedOut();
      else toast(err instanceof Error ? err.message : 'Could not load your plan.', 'error');
    }
  }, [toast, onSignedOut]);

  const act = useCallback(
    async (action: () => Promise<unknown>, done: string) => {
      try {
        await action();
        await reload();
        toast(done);
      } catch (err) {
        toast(err instanceof Error ? err.message : 'Something went wrong.', 'error');
      }
    },
    [reload, toast],
  );

  useEffect(() => {
    void reload();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const stream = api.stream((event) => {
      if (TOAST_EVENTS.has(event.type)) toast(event.message, event.type === 'move_failed' ? 'error' : 'ok');
      clearTimeout(timer);
      timer = setTimeout(reload, 350); // events arrive in bursts; reload once
    });
    return () => {
      clearTimeout(timer);
      stream?.close();
    };
  }, [reload, toast]);

  // The AI writes the advice in the background: check back until it's done
  const running = data?.advice?.status === 'running';
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      const advice = await api.advice().catch(() => null);
      if (advice && advice.status !== 'running') setData((d) => (d ? { ...d, advice } : d));
    }, 2500);
    return () => clearInterval(timer);
  }, [running]);

  return { data, act };
}
