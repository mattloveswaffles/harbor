// Browser storage for the login token and the address picked before signing up.
import type { Place } from './address.ts';
import type { ChatTurn } from './types.ts';

const TOKEN_KEY = 'harbor.token';
const ADDRESS_KEY = 'harbor.address';
const PLACE_KEY = 'harbor.place';
const CHAT_KEY = 'harbor.chat';

function read(store: Storage, key: string): string | null {
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}
function write(store: Storage, key: string, value: string | null): void {
  try {
    value === null ? store.removeItem(key) : store.setItem(key, value);
  } catch {
    /* storage blocked */
  }
}

export const getToken = (): string | null => read(localStorage, TOKEN_KEY);
export function setToken(token: string | null): void {
  write(localStorage, TOKEN_KEY, token);
  if (!token) write(sessionStorage, CHAT_KEY, null); // signing out forgets the conversation
}

export const getDraftAddress = (): string => read(sessionStorage, ADDRESS_KEY) ?? '';
export const saveDraftAddress = (address: string): void => write(sessionStorage, ADDRESS_KEY, address);

export function getDraftPlace(): Place | null {
  try {
    return JSON.parse(read(sessionStorage, PLACE_KEY) ?? 'null') as Place | null;
  } catch {
    return null;
  }
}
export const saveDraftPlace = (place: Place | null): void =>
  write(sessionStorage, PLACE_KEY, place ? JSON.stringify(place) : null);

/** The last 5-digit number in an address, e.g. "2301 Bayshore Blvd, Tampa, FL 33606" -> "33606". */
export function zipFrom(address: string): string | null {
  const matches = address.match(/\b\d{5}\b/g);
  return matches ? (matches[matches.length - 1] ?? null) : null;
}

/** The Ask Harbor conversation, kept per browser tab. */
export function getChat(): ChatTurn[] {
  try {
    return JSON.parse(read(sessionStorage, CHAT_KEY) ?? '[]') as ChatTurn[];
  } catch {
    return [];
  }
}
export const saveChat = (turns: ChatTurn[]): void => write(sessionStorage, CHAT_KEY, JSON.stringify(turns));
