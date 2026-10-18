// Display helpers. Times are Eastern (Florida).
const usd = (dollars: number, digits: number) =>
  dollars.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: digits });

/** Cents as dollars, with cents only when there are some: 42000 -> "$420", 35820 -> "$358.20". */
export const money = (cents: number): string => usd(cents / 100, cents % 100 ? 2 : 0);

/** Cents rounded to whole dollars: 136349 -> "$1,363". */
export const moneyRound = (cents: number): string => usd(Math.round(cents / 100), 0);

/** "Tue 8:07 AM" or "Tue 5 PM" in Eastern time; "—" when missing. */
export const when = (iso: string | null | undefined): string =>
  iso
    ? new Date(iso)
        .toLocaleString('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: 'numeric', minute: '2-digit' })
        .replace(':00', '')
    : '—';

/** 713 -> "11h 53m", 45 -> "45 min". */
export const duration = (minutes: number): string => {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (!h) return `${m} min`;
  return m ? `${h}h ${m}m` : `${h}h`;
};

export const pct = (p: number): string => `${Math.round(p * 100)}%`;
