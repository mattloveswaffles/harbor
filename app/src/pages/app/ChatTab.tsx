// Ask Harbor: chat with the server's agent (it reads the household's own data). Answers stream in.
import { type FormEvent, useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Icon } from '../../components/Icon.tsx';
import { ApiError, api } from '../../lib/api.ts';
import { mark } from '../../lib/assets.ts';
import { getChat, saveChat } from '../../lib/session.ts';
import type { ChatEvent, ChatTurn } from '../../lib/types.ts';
import { ASK_KEY } from './labels.ts';

const PROMPTS = [
  'When should I leave?',
  'Do I have enough cash?',
  'Which shelter takes pets?',
  'What should I approve?',
];

// A new storm pun on every page load.
const PUNS = [
  'Let’s weather this together.',
  'Calm in the eye of the storm.',
  'No forecast is too cloudy for me.',
  'Let’s get you somewhere dry.',
  'Every storm runs out of rain.',
  'Here for you, rain or shine.',
  'Let’s chart a course to calmer skies.',
  'Stay high and dry. I’ll help.',
];
const PUN = PUNS[Math.floor(Math.random() * PUNS.length)];

/** What each tool looks at, as "Checked …" and "Checking …". */
const SOURCES: Record<string, string> = {
  household: 'home',
  household_details: 'household',
  storm_status: 'storm',
  weather_at_home: 'weather',
  bank_accounts: 'bank',
  connected_accounts: 'accounts',
  investments: 'investments',
  evacuation_plan: 'plan',
  evacuation_guide: 'route',
  evacuation_advice: 'advice',
  regenerate_advice: 'advice',
  bills: 'bills',
  nearby_atms: 'ATMs',
  nearby_sensors: 'sensors',
};

interface Turn extends ChatTurn {
  sources?: string[];
  thinking?: string;
  error?: boolean;
}

function failure(err: unknown): string {
  const code = err instanceof ApiError ? err.code : '';
  if (code === 'chat_unavailable') return 'Ask Harbor is off on this server.';
  if (code === 'rate_limited') return 'That’s a lot of questions. Try again in a minute.';
  return 'Harbor couldn’t answer right now. Try again.';
}

/** The answer being written: thinking, the lookups so far and the text. */
interface Live {
  thinking: string;
  tools: string[];
  text: string;
}

function Thinking({ live }: { live: Live }) {
  const tool = live.tools.at(-1);
  return (
    <div className="think">
      <span className="shimmer">{tool ? `Checking your ${SOURCES[tool] ?? 'data'}…` : 'Thinking…'}</span>
      {live.thinking && <p className="think-text">{live.thinking.slice(-280)}</p>}
    </div>
  );
}

function Message({ turn }: { turn: Turn }) {
  if (turn.role === 'user') {
    return (
      <li className="msg user">
        <div className="bubble">{turn.content}</div>
      </li>
    );
  }
  return (
    <li className={`msg bot${turn.error ? ' error' : ''}`}>
      {turn.thinking && (
        <details className="thought">
          <summary>Thought process</summary>
          <p>{turn.thinking}</p>
        </details>
      )}
      <div className="bubble md">
        <Markdown remarkPlugins={[remarkGfm]}>{turn.content}</Markdown>
      </div>
      {turn.sources && turn.sources.length > 0 && <small>Checked {turn.sources.join(' · ')}</small>}
    </li>
  );
}

export default function ChatTab() {
  const [turns, setTurns] = useState<Turn[]>(getChat);
  const [live, setLive] = useState<Live | null>(null);
  const list = useRef<HTMLOListElement>(null);

  useEffect(() => {
    saveChat(turns);
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' });
  }, [turns]);
  useEffect(() => {
    if (live) list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [live]);

  const ask = async (question: string) => {
    const history = [...turns.filter((t) => !t.error), { role: 'user', content: question } as const];
    setTurns((t) => [...t, { role: 'user', content: question }]);
    let state: Live = { thinking: '', tools: [], text: '' };
    setLive(state);
    let error: string | null = null;
    const onEvent = (e: ChatEvent) => {
      if (e.type === 'thinking') state = { ...state, thinking: state.thinking + e.text };
      // Text written before a lookup was the model thinking aloud
      else if (e.type === 'tool')
        state = { thinking: `${state.thinking}${state.text}`, tools: [...state.tools, e.name], text: '' };
      else if (e.type === 'text') state = { ...state, text: state.text + e.text };
      else if (e.type === 'error') error = e.message;
      setLive(state);
    };
    try {
      await api.chat(
        history.map(({ role, content }) => ({ role, content })),
        onEvent,
      );
    } catch (err) {
      error = failure(err);
    }
    const sources = [...new Set(state.tools.map((t) => SOURCES[t] ?? t))];
    setTurns((t) => [
      ...t,
      error || !state.text
        ? { role: 'assistant', content: error ?? failure(null), error: true }
        : { role: 'assistant', content: state.text, sources, thinking: state.thinking.trim() || undefined },
    ]);
    setLive(null);
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: once, on arrival from the quick ask
  useEffect(() => {
    const question = sessionStorage.getItem(ASK_KEY);
    sessionStorage.removeItem(ASK_KEY);
    if (question) void ask(question);
  }, []);

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const input = e.currentTarget.elements.namedItem('question') as HTMLInputElement;
    const question = input.value.trim();
    input.value = '';
    if (question && !live) void ask(question);
  };

  const composer = (
    <form className="composer" onSubmit={onSubmit}>
      <div className="bar">
        <input
          name="question"
          placeholder="Ask about your storm, money or route…"
          maxLength={2000}
          autoComplete="off"
          aria-label="Your question"
        />
        <button className="send" type="submit" aria-label="Send" disabled={Boolean(live)}>
          <Icon name="arrow" />
        </button>
      </div>
    </form>
  );

  if (turns.length === 0 && !live) {
    return (
      <section className="tab chat-page">
        <div className="card chat chat-start">
          <img className="chat-mark" src={mark} alt="" />
          <h2 className="pun">{PUN}</h2>
          {composer}
          <div className="prompts">
            {PROMPTS.map((q) => (
              <button key={q} type="button" className="alt" onClick={() => ask(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="tab chat-page">
      <div className="card chat">
        <ol className="messages" ref={list} aria-live="polite">
          {turns.map((t, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: turns are append-only
            <Message key={i} turn={t} />
          ))}
          {live && (
            <li className="msg bot">
              {live.text ? (
                <div className="bubble md">
                  <Markdown remarkPlugins={[remarkGfm]}>{live.text}</Markdown>
                </div>
              ) : (
                <Thinking live={live} />
              )}
            </li>
          )}
        </ol>
        {composer}
      </div>
    </section>
  );
}
