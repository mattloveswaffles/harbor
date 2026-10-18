// First-run tour: a Storm Dude explains each part of the app while the dashboard shows that tab behind it.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { Icon } from '../../components/Icon.tsx';
import { dudes } from '../../lib/assets.ts';

const STEPS: { dude: keyof typeof dudes; name: string; tab: string; title: string; text: string }[] = [
  {
    dude: 'rumble',
    name: 'Rumble',
    tab: '/app/weather',
    title: 'Hi, I’m Rumble.',
    text: 'Harbor watches every hurricane forecast for your home. When one is coming, we get you out in time and make sure you can pay for it.',
  },
  {
    dude: 'nimbus',
    name: 'Nimbus',
    tab: '/app/accounts',
    title: 'Your money, read-only.',
    text: 'Connect your bank through Nessie. Harbor reads balances to price your trip. Nothing moves until you approve a plan.',
  },
  {
    dude: 'foggy',
    name: 'Foggy',
    tab: '/app/route',
    title: 'Your way out.',
    text: 'When to leave, where to go and which shelters take pets. The map follows the forecast cone as it changes.',
  },
  {
    dude: 'squall',
    name: 'Squall',
    tab: '/app',
    title: 'One tap to approve.',
    text: 'I add up gas, a room, food and the dog, then line up the money from savings and investments. You approve it in one tap.',
  },
  {
    dude: 'twirl',
    name: 'Twirl',
    tab: '/app/chat',
    title: 'Ask me anything.',
    text: 'Questions about your storm, money or route? I answer from your own data, any time.',
  },
];

const KEY = 'harbor.tour';
export const tourSeen = () => localStorage.getItem(KEY) === 'done';

export function Tour({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const [i, setI] = useState(0);
  const step = STEPS[i] ?? STEPS[0];
  const last = i === STEPS.length - 1;

  useEffect(() => {
    if (step) navigate(step.tab);
  }, [navigate, step]);

  const close = () => {
    localStorage.setItem(KEY, 'done');
    navigate('/app');
    onClose();
  };

  if (!step) return null;
  return (
    <div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      <div className="tour-card" key={step.dude}>
        <div className="tour-art">
          <img src={dudes[step.dude]} alt="" />
        </div>
        <div className="tour-body">
          <span className="tour-name">{step.name}</span>
          <h2 id="tour-title">{step.title}</h2>
          <p>{step.text}</p>
          <div className="tour-actions">
            <div className="tour-dots" role="img" aria-label={`Step ${i + 1} of ${STEPS.length}`}>
              {STEPS.map((s, n) => (
                <span key={s.dude} className={n === i ? 'on' : undefined} />
              ))}
            </div>
            {!last && (
              <button className="link" type="button" onClick={close}>
                Skip
              </button>
            )}
            <button className="button" type="button" onClick={() => (last ? close() : setI(i + 1))}>
              {last ? 'Get started' : 'Next'}
              <Icon name="arrow" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
