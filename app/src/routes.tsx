// Lazy routes: each page downloads only its own code.
import type { RouteObject } from 'react-router';
import { SiteLayout } from './components/SiteLayout.tsx';

const page = (load: () => Promise<{ default: React.ComponentType }>) => async () => ({
  Component: (await load()).default,
});

export const routes: RouteObject[] = [
  {
    element: <SiteLayout />,
    children: [
      { index: true, lazy: page(() => import('./pages/Home.tsx')) },
      { path: 'how-it-works', lazy: page(() => import('./pages/HowItWorks.tsx')) },
      { path: 'impact', lazy: page(() => import('./pages/Impact.tsx')) },
      { path: '*', lazy: page(() => import('./pages/NotFound.tsx')) },
    ],
  },
  { path: 'signin', lazy: page(() => import('./pages/SignIn.tsx')) },
  {
    path: 'app',
    lazy: page(() => import('./pages/app/AppRoot.tsx')),
    children: [
      { index: true, lazy: page(() => import('./pages/app/PlanTab.tsx')) },
      { path: 'weather', lazy: page(() => import('./pages/app/WeatherTab.tsx')) },
      { path: 'accounts', lazy: page(() => import('./pages/app/AccountsTab.tsx')) },
      { path: 'route', lazy: page(() => import('./pages/app/RouteTab.tsx')) },
      { path: 'shelters', lazy: page(() => import('./pages/app/SheltersTab.tsx')) },
      { path: 'chat', lazy: page(() => import('./pages/app/ChatTab.tsx')) },
    ],
  },
];
