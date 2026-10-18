import { type FormEvent, type KeyboardEvent, useEffect, useId, useState } from 'react';
import { locateNearby, type Place, resolvePlace, type Suggestion, suggest } from '../lib/address.ts';
import { Icon } from './Icon.tsx';

interface Props {
  cta: string;
  initial?: string;
  placeholder?: string;
  busy?: boolean;
  /** A suggestion was picked and resolved. */
  onPlace: (place: Place) => void;
  /** Submitted without picking a suggestion. */
  onText: (text: string) => void;
  delay?: number;
  /** Ask for the user's location on focus, to suggest nearby addresses first. */
  nearby?: boolean;
}

export function AddressSearch({
  cta,
  initial = '',
  placeholder = 'Enter your home address',
  busy,
  onPlace,
  onText,
  delay = 200,
  nearby,
}: Props) {
  const id = useId();
  const [text, setText] = useState(initial);
  const [items, setItems] = useState<Suggestion[]>([]);
  const [active, setActive] = useState(-1);
  const [query, setQuery] = useState('');
  const [resolving, setResolving] = useState(false);

  // Debounced lookup; a newer query cancels the older one.
  useEffect(() => {
    if (query.trim().length < 3) return setItems([]);
    let current = true;
    const timer = setTimeout(async () => {
      const next = await suggest(query);
      if (current) {
        setItems(next);
        setActive(-1);
      }
    }, delay);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [query, delay]);

  const pick = async (s: Suggestion) => {
    setText(s.label);
    setItems([]);
    setResolving(true);
    const place = await resolvePlace(s);
    setResolving(false);
    if (place) {
      setText(place.label);
      onPlace(place);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!items.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length);
    } else if (e.key === 'Enter' && items[active]) {
      e.preventDefault();
      void pick(items[active]);
    } else if (e.key === 'Escape') setItems([]);
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim()) onText(text.trim());
  };

  const open = items.length > 0;
  return (
    <form className={`search has-suggest${resolving ? ' loading' : ''}`} onSubmit={onSubmit}>
      <Icon name="location" />
      <input
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setQuery(e.target.value);
        }}
        onKeyDown={onKeyDown}
        onFocus={nearby ? locateNearby : undefined}
        onBlur={() => setTimeout(() => setItems([]), 100)}
        placeholder={placeholder}
        required
        maxLength={180}
        autoComplete="off"
        aria-label="Your home address"
        role="combobox"
        aria-autocomplete="list"
        aria-controls={id}
        aria-expanded={open}
        aria-activedescendant={active >= 0 ? `${id}-${active}` : undefined}
      />
      <button className="button" type="submit" disabled={busy}>
        <span className="label">{cta}</span>
        <Icon name="arrow" />
      </button>
      {open && (
        <div className="suggest" id={id} role="listbox">
          {items.map((s, i) => {
            const [street, ...rest] = s.label.split(', ');
            return (
              <div
                key={s.key}
                id={`${id}-${i}`}
                role="option"
                tabIndex={-1}
                aria-selected={i === active}
                onMouseDown={(e) => {
                  e.preventDefault();
                  void pick(s);
                }}
              >
                <Icon name="pin" />
                <span>
                  <b>{street}</b>
                  <small>{rest.join(', ')}</small>
                </span>
              </div>
            );
          })}
        </div>
      )}
    </form>
  );
}
