// Typed client for the Harbor server.
import { API_ORIGIN } from './config.ts';
import { getToken, setToken } from './session.ts';
import type {
  Account,
  Advice,
  Atm,
  AuthOut,
  ChatEvent,
  ChatTurn,
  Connection,
  Guide,
  HarborEvent,
  Health,
  MapOut,
  Plan,
  Portfolio,
  Profile,
  ProfileSave,
  StormStatus,
  User,
  Weather,
  ZipInfo,
} from './types.ts';

const BASE = `${API_ORIGIN}/api/v1`;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

function authHeaders(body?: unknown): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  return headers;
}

async function failed(res: Response): Promise<ApiError> {
  const json: unknown = await res.json().catch(() => null);
  const err = (json as { error?: { code?: string; message?: string } } | null)?.error;
  if (res.status === 401) setToken(null);
  return new ApiError(res.status, err?.code ?? `http_${res.status}`, err?.message ?? res.statusText);
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers = authHeaders(body);

  let res: Response;
  try {
    res = await fetch(path === '/health' ? API_ORIGIN + path : BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'network', 'Harbor is unreachable. Check your connection.');
  }
  if (res.status === 204) return undefined as T;
  if (!res.ok) throw await failed(res);
  return (await res.json().catch(() => null)) as T;
}

const get = <T>(path: string) => request<T>('GET', path);
const post = <T>(path: string, body: unknown = {}) => request<T>('POST', path, body);
const put = <T>(path: string, body: unknown) => request<T>('PUT', path, body);
const del = <T>(path: string) => request<T>('DELETE', path);

export const api = {
  health: () => get<Health>('/health'),
  zip: (zip: string) => get<ZipInfo>(`/zip/${encodeURIComponent(zip)}`),

  signup: (body: {
    name: string;
    email: string;
    password: string;
    zip: string;
    location?: { lat: number; lon: number };
  }) => post<AuthOut>('/auth/signup', body),
  login: (email: string, password: string) => post<AuthOut>('/auth/login', { email, password }),
  logout: () => post<void>('/auth/logout'),

  me: () => get<User>('/me'),
  updateZip: (zip: string) => request<User>('PATCH', '/me', { zip }),
  accounts: () => get<Account[]>('/me/accounts'),
  portfolio: () => get<Portfolio>('/me/portfolio'),
  storm: () => get<StormStatus>('/me/storm'),
  map: () => get<MapOut>('/me/map'),
  events: (limit = 30) => get<HarborEvent[]>(`/me/events?limit=${limit}`),
  weather: () => get<Weather>('/me/weather'),
  atms: () => get<Atm[]>('/me/atms'),

  profile: () => get<Profile>('/me/profile'),
  saveProfile: (profile: ProfileSave) => put<Profile>('/me/profile', profile),
  connections: () => get<Connection[]>('/me/connections'),
  connect: (id: string) => post<Connection[]>(`/me/connections/${id}`),
  disconnect: (id: string) => del<Connection[]>(`/me/connections/${id}`),
  advice: () => get<Advice>('/me/advice'),
  regenerate: () => post<Advice>('/me/advice/regenerate'),

  plan: async () => (await get<{ plan: Plan | null }>('/me/plan')).plan,
  approve: (version: number) => post<unknown>('/me/plan/approve', { plan_version: version }),
  /** Ask Harbor: streams the answer as server-sent events (thinking, tools, text, then done or error). */
  async chat(messages: ChatTurn[], onEvent: (e: ChatEvent) => void): Promise<void> {
    let res: Response;
    try {
      res = await fetch(`${BASE}/me/chat`, {
        method: 'POST',
        headers: authHeaders({}),
        body: JSON.stringify({ messages }),
      });
    } catch {
      throw new ApiError(0, 'network', 'Harbor is unreachable. Check your connection.');
    }
    if (!res.ok || !res.body) throw await failed(res);
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      const frames = buffer.split('\n\n');
      buffer = frames.pop() ?? '';
      for (const frame of frames) if (frame.startsWith('data: ')) onEvent(JSON.parse(frame.slice(6)) as ChatEvent);
    }
  },
  cancelPlan: () => post<unknown>('/me/plan/cancel'),

  evacuation: async () => {
    const res = await get<Guide | { guide: null }>('/me/evacuation');
    return 'guide' in res ? null : res;
  },
  chooseDestination: (id: string) =>
    post<Guide | { guide: null }>('/me/evacuation/destination', { destination_id: id }),

  /** Live updates (Server-Sent Events). EventSource can't send headers, so the token goes in the URL. */
  stream(onEvent: (e: HarborEvent) => void): EventSource | null {
    const token = getToken();
    if (!token) return null;
    const source = new EventSource(`${BASE}/me/events/stream?token=${encodeURIComponent(token)}`);
    source.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data) as HarborEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    return source;
  },
};
