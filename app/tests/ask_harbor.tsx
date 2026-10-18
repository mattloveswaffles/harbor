// Ask Harbor: streams answers as Markdown, shows what the agent checked and thought, and handles errors.
import { beforeEach, expect, test } from 'bun:test';
import type { ChatEvent } from '../src/lib/types.ts';
import { mockFetch, render, setupDom } from './support/dom.ts';

setupDom('http://localhost:3000/app/chat');
const { act } = await import('react');
const { default: ChatTab } = await import('../src/pages/app/ChatTab.tsx');
const { DashboardContext } = await import('../src/pages/app/useHarbor.ts');
type Dashboard = NonNullable<React.ContextType<typeof DashboardContext>>;

/** A streamed /me/chat answer. */
const stream = (...events: ChatEvent[]) =>
  new Response(events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(''), {
    headers: { 'Content-Type': 'text/event-stream' },
  });

async function open() {
  const value = { data: {}, act: async () => undefined } as unknown as Dashboard;
  const view = await render(
    <DashboardContext value={value}>
      <ChatTab />
    </DashboardContext>,
  );
  const send = async (text: string) => {
    const input = view.container.querySelector('input') as HTMLInputElement;
    input.value = text;
    await act(async () => void view.container.querySelector('form')?.requestSubmit());
    await view.settle();
  };
  const bubbles = () => [...view.container.querySelectorAll('.msg .bubble')].map((b) => b.textContent);
  return { ...view, send, bubbles };
}

beforeEach(() => sessionStorage.clear());

test('starts with a pun, the chat bar and prompts, not canned messages', async () => {
  const chat = await open();
  expect(chat.bubbles()).toEqual([]);
  expect(chat.container.querySelector('.pun')?.textContent).toBeTruthy();
  expect(chat.container.querySelector('.chat-start form .bar .send')).not.toBeNull();
  expect(chat.container.querySelectorAll('.prompts button').length).toBe(4);
  await chat.unmount();
});

test('streams the answer as Markdown and shows what the agent checked and thought', async () => {
  const calls = mockFetch(() =>
    stream(
      { type: 'thinking', text: 'Look at the bank.' },
      { type: 'text', text: 'Let me check.' },
      { type: 'tool', name: 'bank_accounts' },
      { type: 'text', text: 'You have **$920** ' },
      { type: 'text', text: 'in cash.' },
      { type: 'done', tools_used: ['bank_accounts'] },
    ),
  );
  const chat = await open();
  await chat.send('How much cash do I have?');
  expect(chat.bubbles()).toEqual(['How much cash do I have?', 'You have $920 in cash.']);
  expect(chat.container.querySelector('.msg.bot .bubble strong')?.textContent).toBe('$920');
  // The work sits above the answer, folded into one line that opens to each step
  const work = chat.container.querySelector('.msg.bot > .work:first-child') as HTMLElement;
  const lines = () => [...work.querySelectorAll('.work-line')].map((l) => l.textContent);
  expect(work.querySelector('.work-summary')?.textContent).toMatch(/^Thought for \d+s$/);
  expect(lines()).toEqual([]);
  await act(async () => (work.querySelector('.work-summary') as HTMLButtonElement).click());
  expect(lines()).toEqual(['Thought', 'Checked your bank']);
  await act(async () => (work.querySelector('button.work-line') as HTMLButtonElement).click());
  expect(work.querySelector('.work-detail')?.textContent).toBe('Look at the bank.\n\nLet me check.');

  await chat.send('Is that enough?');
  const body = JSON.parse(String(calls.at(-1)?.init?.body));
  expect(body.messages).toEqual([
    { role: 'user', content: 'How much cash do I have?' },
    { role: 'assistant', content: 'You have **$920** in cash.' },
    { role: 'user', content: 'Is that enough?' },
  ]);
  await chat.unmount();
});

test('errors show as errors and are not sent back as history', async () => {
  const calls = mockFetch(() =>
    stream({ type: 'error', code: 'chat_failed', message: 'Harbor couldn’t answer right now.' }),
  );
  const chat = await open();
  await chat.send('Hi');
  expect(chat.container.querySelector('.msg.error')?.textContent).toContain('couldn’t answer');
  await chat.send('Hello?');
  expect(JSON.parse(String(calls.at(-1)?.init?.body)).messages).toHaveLength(2);
  await chat.unmount();
});

test('when chat is off on the server, sending says so', async () => {
  mockFetch(() => Response.json({ error: { code: 'chat_unavailable', message: 'x' } }, { status: 503 }));
  const chat = await open();
  await chat.send('Hi');
  expect(chat.container.querySelector('.msg.error')?.textContent).toBe('Ask Harbor is off on this server.');
  await chat.unmount();
});
