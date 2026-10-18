// Test helper: a browser-like DOM (happy-dom) and a React render that waits for effects and lazy routes.
import { afterAll, beforeAll } from 'bun:test';
import { GlobalRegistrator } from '@happy-dom/global-registrator';
import type { ReactNode } from 'react';

export function setupDom(url = 'http://localhost:3000/') {
  beforeAll(() => {
    GlobalRegistrator.register({ url });
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  });
  afterAll(() => GlobalRegistrator.unregister());
}

export async function render(ui: ReactNode) {
  const { act } = await import('react');
  const { createRoot } = await import('react-dom/client');
  document.body.innerHTML = '<div id="root"></div>';
  const root = createRoot(document.getElementById('root') as HTMLElement);
  await act(async () => root.render(ui));
  return {
    container: document.getElementById('root') as HTMLElement,
    /** Let pending promises (fetches, lazy routes) settle and re-render. */
    settle: () => act(() => new Promise((r) => setTimeout(r, 30))),
    unmount: () => act(() => root.unmount()),
  };
}

/** Replace fetch with a handler; returns the calls made. */
export function mockFetch(handler: (url: URL, init?: RequestInit) => Response | Promise<Response>) {
  const calls: { url: URL; init?: RequestInit }[] = [];
  globalThis.fetch = (async (input: string | URL, init?: RequestInit) => {
    const url = new URL(String(input), location.href);
    calls.push({ url, init });
    return handler(url, init);
  }) as typeof fetch;
  return calls;
}
