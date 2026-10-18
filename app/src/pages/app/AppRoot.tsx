// /app: no server -> offline note; signed in -> dashboard; otherwise onboarding.
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router';
import { api } from '../../lib/api.ts';
import { getToken, setToken } from '../../lib/session.ts';
import type { Health } from '../../lib/types.ts';
import { Dashboard } from './Dashboard.tsx';
import { Onboarding } from './Onboarding.tsx';
import { ToastProvider } from './toast.tsx';
import { Loading } from './ui.tsx';

/** A sign-in link (/app#token=…, from seed.sh): keep the token, drop it from the address bar. */
function tokenFromLink(): void {
  const token = new URLSearchParams(location.hash.slice(1)).get('token');
  if (!token) return;
  setToken(token);
  history.replaceState(null, '', location.pathname);
}

function Offline() {
  return (
    <Loading page>
      <p className="offline">
        <b>The Harbor server isn’t reachable.</b>
        <br />
        Run the full app with <code>docker run -p 3000:3000 harbor</code>.
        <br />
        <Link to="/">Back to the site</Link>
      </p>
    </Loading>
  );
}

export default function AppRoot() {
  const [health, setHealth] = useState<Health | null | undefined>(undefined);
  const [signedIn, setSignedIn] = useState(() => {
    tokenFromLink();
    return Boolean(getToken());
  });

  useEffect(() => {
    let current = true;
    api.health().then(
      (h) => current && setHealth(h),
      () => current && setHealth(null),
    );
    return () => {
      current = false;
    };
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    setSignedIn(false);
  }, []);

  if (!health) return <div className="harbor-app">{health === undefined ? <Loading page /> : <Offline />}</div>;
  return (
    <div className="harbor-app">
      <ToastProvider>
        <title>Harbor</title>
        {signedIn ? (
          <Dashboard health={health} onSignedOut={signOut} />
        ) : (
          <Onboarding onSignedIn={() => setSignedIn(true)} />
        )}
      </ToastProvider>
    </div>
  );
}
