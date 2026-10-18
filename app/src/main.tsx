import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router';
import { IconSprite } from './components/Icon.tsx';
import { BASE_PATH } from './lib/config.ts';
import { routes } from './routes.tsx';
import 'leaflet/dist/leaflet.css';
import './styles/site.css';
import './styles/effects.css';
import './styles/app.css';

const router = createBrowserRouter(routes, { basename: BASE_PATH || '/' });
const root = document.getElementById('root');

if (root) {
  createRoot(root).render(
    <StrictMode>
      <IconSprite />
      <RouterProvider router={router} />
    </StrictMode>,
  );
}
