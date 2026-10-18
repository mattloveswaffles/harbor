// Formatting: money, times, durations and address parsing.
import { describe, expect, test } from 'bun:test';
import { tidy } from '../src/lib/address.ts';
import { duration, money, moneyRound, pct, when } from '../src/lib/format.ts';
import { zipFrom } from '../src/lib/session.ts';

describe('money', () => {
  test('shows cents only when there are some', () => {
    expect(money(42000)).toBe('$420');
    expect(money(35820)).toBe('$358.20');
    expect(money(0)).toBe('$0');
  });
  test('rounds to whole dollars with separators', () => {
    expect(moneyRound(136349)).toBe('$1,363');
    expect(moneyRound(136350)).toBe('$1,364');
  });
});

describe('time', () => {
  test('shows Eastern time and drops :00', () => {
    expect(when('2024-10-08T12:07:00Z')).toBe('Tue 8:07 AM');
    expect(when('2024-10-08T21:00:00Z')).toBe('Tue 5 PM');
  });
  test('handles a missing time', () => {
    expect(when(null)).toBe('—');
  });
  test('durations', () => {
    expect(duration(713)).toBe('11h 53m');
    expect(duration(120)).toBe('2h');
    expect(duration(45)).toBe('45 min');
  });
  test('percent', () => {
    expect(pct(0.684)).toBe('68%');
  });
});

describe('text', () => {
  test('finds the ZIP at the end of an address', () => {
    expect(zipFrom('2301 Bayshore Blvd, Tampa, FL 33606')).toBe('33606');
    expect(zipFrom('12345 Main St, 33602')).toBe('33602');
    expect(zipFrom('Tampa, FL')).toBeNull();
  });
  test('tidies geocoder labels', () => {
    expect(tidy('2301 Bayshore Blvd, Tampa, FL, 33629, USA')).toBe('2301 Bayshore Blvd, Tampa, FL 33629');
  });
});
