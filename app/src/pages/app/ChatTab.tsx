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
import { type Step, Work } from './Work.tsx';

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

interface Turn extends ChatTurn {
  steps?: Step[];
  seconds?: number;
  error?: boolean;
}

function failure(err: unknown): string {
  const code = err instanceof ApiError ? err.code : '';
  if (code === 'chat_unavailable') return 'Ask Harbor is off on this server.';
  if (code === 'rate_limited') return 'That’s a lot of questions. Try again in a minute.';
  return 'Harbor couldn’t answer right now. Try again.';
}

/** The answer being written: its steps so far, the text, and how long the work took once the text began. */
interface Live {
  steps: Step[];
  text: string;
  seconds?: number;
}

/** The answer with one more event in it: thinking joins the thought under way, a lookup starts a new step. */
function advance(state: Live, e: ChatEvent, started: number): Live {
  const last = state.steps.at(-1);
  if (e.type === 'thinking') {
    const thought = last && 'thinking' in last ? { thinking: last.thinking + e.text } : null;
    return {
      ...state,
      steps: thought ? [...state.steps.slice(0, -1), thought] : [...state.steps, { thinking: e.text }],
    };
  }
  // Text written before a lookup was the model thinking aloud
  if (e.type === 'tool') {
    const aloud = state.text.trim();
    const steps: Step[] = !aloud
      ? state.steps
      : last && 'thinking' in last
        ? [...state.steps.slice(0, -1), { thinking: `${last.thinking}\n\n${aloud}` }]
        : [...state.steps, { thinking: aloud }];
    return { steps: [...steps, { tool: e.name }], text: '' };
  }
  if (e.type === 'text')
    return {
      ...state,
      text: state.text + e.text,
      seconds: state.seconds ?? Math.max(1, Math.round((Date.now() - started) / 1000)),
    };
  return state;
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
      {turn.steps && <Work steps={turn.steps} working={false} seconds={turn.seconds} />}
      <div className="bubble md">
        <Markdown remarkPlugins={[remarkGfm]}>{turn.content}</Markdown>
      </div>
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
    let state: Live = { steps: [], text: '' };
    setLive(state);
    let error: string | null = null;
    const started = Date.now();
    const onEvent = (e: ChatEvent) => {
      if (e.type === 'error') error = e.message;
      state = advance(state, e, started);
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
    setTurns((t) => [
      ...t,
      error || !state.text
        ? { role: 'assistant', content: error ?? failure(null), error: true }
        : { role: 'assistant', content: state.text, steps: state.steps, seconds: state.seconds },
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
              <Work steps={live.steps} working={!live.text} seconds={live.seconds} />
              {live.text && (
                <div className="bubble md">
                  <Markdown remarkPlugins={[remarkGfm]}>{live.text}</Markdown>
                </div>
              )}
            </li>
          )}
        </ol>
        {composer}
      </div>
    </section>
  );
}
