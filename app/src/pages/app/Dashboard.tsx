import { type FormEvent, lazy, Suspense, useCallback, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate, useNavigation } from 'react-router';
import { Icon, type IconName } from '../../components/Icon.tsx';
import { Brand } from '../../components/SiteLayout.tsx';
import { api } from '../../lib/api.ts';
import { ASK_KEY } from './labels.ts';
import { Tour, tourSeen } from './Tour.tsx';
import { Loading } from './ui.tsx';
import { DashboardContext, type SettingsTab, useHarbor } from './useHarbor.ts';

const Settings = lazy(async () => ({ default: (await import('./Settings.tsx')).Settings }));

const TABS: [path: string, label: string, icon: IconName][] = [
  ['', 'My plan', 'shield'],
  ['weather', 'Weather', 'rain'],
  ['accounts', 'Accounts', 'bank'],
  ['route', 'Route', 'route'],
  ['shelters', 'Shelters', 'tent'],
  ['chat', 'Ask Harbor', 'harbor'],
];

function Avatar() {
  return (
    <svg className="av-blob" aria-hidden="true" viewBox="0 0 100 100" width="36" height="36">
      <path
        fill="#f6a27c"
        d="M87.5 50.72C87.5 70.84 71.91 86.14 51.41 86.14C30.9 86.14 15.31 70.84 15.31 50.72C15.31 30.59 30.9 15.29 51.41 15.29C71.91 15.29 87.5 30.59 87.5 50.72Z"
      />
      <path
        fill="#1b1310"
        d="M40.39 48.22C39.22 56.21 35.64 55.68 35.64 55.68C32.06 55.16 33.23 47.17 33.23 47.17C34.39 39.18 37.97 39.7 37.97 39.7C41.55 40.23 40.39 48.22 40.39 48.22Z"
      />
      <path
        fill="#1b1310"
        d="M63.42 47.08C61.99 54.16 58.35 53.42 58.35 53.42C54.72 52.68 56.15 45.61 56.15 45.61C57.59 38.53 61.22 39.26 61.22 39.26C64.86 40 63.42 47.08 63.42 47.08Z"
      />
    </svg>
  );
}

/** "Ask Harbor anything": hands the question to the chat tab. */
function QuickAsk() {
  const navigate = useNavigate();
  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const input = e.currentTarget.elements.namedItem('q') as HTMLInputElement;
    const q = input.value.trim();
    if (!q) return;
    sessionStorage.setItem(ASK_KEY, q);
    input.value = '';
    navigate('/app/chat');
  };
  return (
    <form className="quick-ask" onSubmit={onSubmit}>
      <Icon name="harbor" />
      <input name="q" placeholder="Ask Harbor anything…" autoComplete="off" aria-label="Ask Harbor" />
    </form>
  );
}

export function Dashboard({ onSignedOut }: { onSignedOut: () => void }) {
  const { data, act } = useHarbor(onSignedOut);
  const { pathname } = useLocation();
  const navigation = useNavigation();
  const [touring, setTouring] = useState(() => !tourSeen());
  const [settings, setSettings] = useState<SettingsTab | null>(null);
  const openSettings = useCallback((tab: SettingsTab = 'you') => setSettings(tab), []);
  const context = useMemo(() => (data ? { data, act, openSettings } : null), [data, act, openSettings]);

  if (!context || !data) return <Loading page />;

  const [path, title] = TABS.find(([p]) => p && pathname.endsWith(`/${p}`)) ?? ['', 'My plan'];
  const chat = path === 'chat';
  const signOut = async () => {
    await api.logout().catch(() => undefined);
    onSignedOut();
  };

  return (
    <DashboardContext value={context}>
      <div className="shell">
        <aside className="side">
          <Brand />
          <nav className="tabs" aria-label="Sections">
            {TABS.map(([path, label, icon]) => (
              <NavLink key={label} className="side-link" to={path ? `/app/${path}` : '/app'} end>
                <Icon name={icon} />
                {label}
                {!path && data.plan?.status === 'awaiting_approval' && (
                  <span className="dot-badge" title="Needs approval" />
                )}
              </NavLink>
            ))}
          </nav>
          <div className="side-user">
            <button className="me" type="button" onClick={() => openSettings('you')}>
              <Avatar />
              <span className="who">
                {data.user.name}
                <small>{data.place ? `${data.place.city}, ${data.place.state} ${data.user.zip}` : data.user.zip}</small>
              </span>
            </button>
            <button className="icon-btn" type="button" title="Sign out" aria-label="Sign out" onClick={signOut}>
              <Icon name="logout" />
            </button>
          </div>
        </aside>
        <main className="main">
          <header className="topbar">
            <h1>{title}</h1>
            <span className="spacer" />
            {!chat && <QuickAsk />}
            <button
              className="icon-btn round"
              type="button"
              title="Settings"
              aria-label="Settings"
              onClick={() => openSettings()}
            >
              <Icon name="settings" />
            </button>
          </header>
          {navigation.state === 'loading' ? <Loading /> : <Outlet />}
        </main>
      </div>
      {settings && (
        <Suspense>
          <Settings tab={settings} onTab={setSettings} onClose={() => setSettings(null)} />
        </Suspense>
      )}
      {touring && <Tour onClose={() => setTouring(false)} />}
    </DashboardContext>
  );
}
