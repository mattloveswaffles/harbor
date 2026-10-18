// API client: auth header, error envelope, 401 sign-out and the live stream URL.
import { afterEach, describe, expect, mock, test } from 'bun:test';
import { setupDom } from './support/dom.ts';

setupDom('http://localhost:3000/app');

const { api, ApiError } = await import('../src/lib/api.ts');
const { getToken, setToken } = await import('../src/lib/session.ts');

const reply = (status: number, body?: unknown) =>
  mock(async (_url: string, _init?: RequestInit) =>
    body === undefined ? new Response(null, { status }) : Response.json(body, { status }),
  );

afterEach(() => setToken(null));

describe('requests', () => {
  test('sends the token and parses JSON', async () => {
    setToken('hbr_test');
    const fetch = reply(200, [{ id: 'acc_1', balance_cents: 42000 }]);
    globalThis.fetch = fetch as unknown as typeof globalThis.fetch;
    const accounts = await api.accounts();
    expect(accounts[0]?.balance_cents).toBe(42000);
    const [url, init] = fetch.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/me/accounts');
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer hbr_test');
  });

  test('posts JSON bodies', async () => {
    const fetch = reply(200, { ok: true });
    globalThis.fetch = fetch as unknown as typeof globalThis.fetch;
    await api.approve(3);
    const [, init] = fetch.mock.calls[0] ?? [];
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ plan_version: 3 });
  });

  test('unwraps { plan } and { guide: null }', async () => {
    globalThis.fetch = reply(200, { plan: null }) as unknown as typeof globalThis.fetch;
    expect(await api.plan()).toBeNull();
    globalThis.fetch = reply(200, { guide: null }) as unknown as typeof globalThis.fetch;
    expect(await api.evacuation()).toBeNull();
  });
});

describe('errors', () => {
  test('turns the error envelope into an ApiError', async () => {
    globalThis.fetch = reply(409, {
      error: { code: 'plan_version_stale', message: 'Reload.', fields: null },
    }) as unknown as typeof globalThis.fetch;
    const err = await api.approve(1).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, code: 'plan_version_stale', message: 'Reload.' });
  });

  test('a 401 clears the stored token', async () => {
    setToken('hbr_old');
    globalThis.fetch = reply(401, {
      error: { code: 'invalid_token', message: 'Expired.' },
    }) as unknown as typeof globalThis.fetch;
    await api.me().catch(() => undefined);
    expect(getToken()).toBeNull();
  });

  test('network failures say the server is unreachable', async () => {
    globalThis.fetch = mock(async () => {
      throw new TypeError('offline');
    }) as unknown as typeof globalThis.fetch;
    expect(await api.health().catch((e: unknown) => e)).toMatchObject({ status: 0, code: 'network' });
  });

  test('204 responses resolve to undefined', async () => {
    globalThis.fetch = reply(204) as unknown as typeof globalThis.fetch;
    expect(await api.logout()).toBeUndefined();
  });
});

describe('live stream', () => {
  test('needs a token and passes it in the URL', () => {
    globalThis.EventSource = class {
      onmessage = null;
      constructor(readonly url: string) {}
      close() {}
    } as unknown as typeof EventSource;
    expect(api.stream(() => undefined)).toBeNull();
    setToken('hbr_live');
    const source = api.stream(() => undefined);
    expect(source?.url).toContain('/api/v1/me/events/stream?token=hbr_live');
    source?.close();
  });
});
