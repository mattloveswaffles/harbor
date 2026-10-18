// Address search: suggestions render while typing, keys and clicks pick one, and the place resolves.
import { expect, test } from 'bun:test';
import type { Place } from '../src/lib/address.ts';
import { mockFetch, render, setupDom } from './support/dom.ts';

setupDom();
const { act } = await import('react');
const { AddressSearch } = await import('../src/components/AddressSearch.tsx');

const SUGGESTIONS = {
  suggestions: [
    { text: '2301 Bayshore Blvd, Tampa, FL, 33629, USA', magicKey: 'k1' },
    { text: '2301 Bayshore Blvd, Dunedin, FL, 34698, USA', magicKey: 'k2' },
  ],
};
const candidate = (city: string, zip: string) => ({
  candidates: [
    {
      location: { x: -82.48, y: 27.93 },
      attributes: { StAddr: '2301 Bayshore Blvd', City: city, RegionAbbr: 'FL', Postal: zip },
    },
  ],
});

async function setup() {
  mockFetch((url) => {
    if (url.pathname.endsWith('/suggest')) return Response.json(SUGGESTIONS);
    return Response.json(
      url.searchParams.get('magicKey') === 'k2' ? candidate('Dunedin', '34698') : candidate('Tampa', '33629'),
    );
  });
  const picked: Place[] = [];
  const typed: string[] = [];
  const view = await render(
    <AddressSearch cta="Go" delay={0} onPlace={(p) => picked.push(p)} onText={(t) => typed.push(t)} />,
  );
  const input = view.container.querySelector('input') as HTMLInputElement;
  const type = async (text: string) => {
    await act(async () => {
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setValue?.call(input, text);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await view.settle();
  };
  const key = (k: string) =>
    act(async () => void input.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true })));
  const options = () => [...view.container.querySelectorAll('[role=option]')].map((li) => li.textContent);
  return { ...view, input, picked, typed, type, key, options };
}

test('typing shows tidy suggestions; short input shows none', async () => {
  const s = await setup();
  await s.type('ab');
  expect(s.options()).toEqual([]);
  await s.type('2301 bayshore');
  expect(s.options()).toEqual(['2301 Bayshore BlvdTampa, FL 33629', '2301 Bayshore BlvdDunedin, FL 34698']);
  expect(s.input.getAttribute('aria-expanded')).toBe('true');
});

test('arrow keys + Enter pick a suggestion and resolve its ZIP and point', async () => {
  const s = await setup();
  await s.type('2301 bayshore');
  await s.key('ArrowDown');
  await s.key('ArrowDown');
  await s.key('Enter');
  await s.settle();
  expect(s.picked).toEqual([
    {
      label: '2301 Bayshore Blvd, Dunedin, FL 34698',
      zip: '34698',
      city: 'Dunedin',
      state: 'FL',
      lat: 27.93,
      lon: -82.48,
    },
  ]);
  expect(s.input.value).toBe('2301 Bayshore Blvd, Dunedin, FL 34698');
  expect(s.options()).toEqual([]);
});

test('a click picks too, and Escape closes the list', async () => {
  const s = await setup();
  await s.type('2301 bayshore');
  await s.key('Escape');
  expect(s.options()).toEqual([]);
  await s.type('2301 bayshore b');
  await act(
    async () =>
      void s.container.querySelector('[role=option]')?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })),
  );
  await s.settle();
  expect(s.picked[0]?.zip).toBe('33629');
});

test('submitting without picking hands over the typed text', async () => {
  const s = await setup();
  await s.type('Tampa, FL 33606');
  await act(async () => void s.container.querySelector('form')?.requestSubmit());
  expect(s.typed).toEqual(['Tampa, FL 33606']);
});
