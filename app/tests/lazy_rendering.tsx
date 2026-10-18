// Lazy rendering: every route loads its own code on demand and renders the right page.
import { describe, expect, test } from 'bun:test';
import { mockFetch, render, setupDom } from './support/dom.ts';

setupDom();
const { createMemoryRouter, RouterProvider } = await import('react-router');
const { routes } = await import('../src/routes.tsx');

async function open(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const view = await render(<RouterProvider router={router} />);
  await view.settle(); // the lazy route's code
  await view.settle(); // its first data
  return { ...view, router, text: () => view.container.textContent ?? '' };
}

describe('site pages', () => {
  test.each([
    ['/', 'Harbor turns a hurricane warning into a plan to leave'],
    ['/how-it-works', 'Forecasts in.'],
    ['/impact', 'More people out in time.'],
    ['/signin', 'Sign in'],
    ['/nope', 'Page not found.'],
  ])('%s renders', async (path, heading) => {
    const page = await open(path);
    expect(page.container.querySelector('h1')?.textContent).toContain(heading);
    await page.unmount();
  });

  test('the header marks the current page', async () => {
    const page = await open('/impact');
    expect(page.container.querySelector('.nav [aria-current=page]')?.textContent).toBe('Impact');
    await page.unmount();
  });

  test('links navigate without a reload', async () => {
    const page = await open('/');
    const link = page.container.querySelector('a[href="/how-it-works"]') as HTMLAnchorElement;
    link.click();
    await page.settle();
    expect(page.router.state.location.pathname).toBe('/how-it-works');
    expect(page.text()).toContain('Forecasts in.');
    await page.unmount();
  });
});

describe('app', () => {
  test('explains when the server is unreachable', async () => {
    mockFetch(() => Promise.reject(new TypeError('offline')));
    const page = await open('/app');
    expect(page.text()).toContain('The Harbor server isn’t reachable.');
    await page.unmount();
  });

  test('starts onboarding when signed out', async () => {
    localStorage.clear();
    sessionStorage.clear();
    mockFetch((url) =>
      url.pathname === '/health'
        ? Response.json({ ok: true, mode: 'demo', nessie: 'ok' })
        : new Response(null, { status: 404 }),
    );
    const page = await open('/app');
    expect(page.text()).toContain('Where are you starting?');
    await page.unmount();
  });
});
