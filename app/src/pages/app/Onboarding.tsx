import { type FormEvent, useEffect, useState } from 'react';
import { AddressSearch } from '../../components/AddressSearch.tsx';
import { Icon } from '../../components/Icon.tsx';
import { Brand } from '../../components/SiteLayout.tsx';
import { firstPlace, type Place } from '../../lib/address.ts';
import { ApiError, api } from '../../lib/api.ts';
import { shorePhoto } from '../../lib/assets.ts';
import {
  getDraftAddress,
  getDraftPlace,
  saveDraftAddress,
  saveDraftPlace,
  setToken,
  zipFrom,
} from '../../lib/session.ts';

/** Check the ZIP is one Harbor covers; returns an error message or null. */
async function covered(place: Place): Promise<string | null> {
  try {
    await api.zip(place.zip);
    return null;
  } catch (err) {
    if (err instanceof ApiError && (err.code === 'zip_not_supported' || err.status === 422)) {
      return 'We couldn’t find that address. Try including the ZIP.';
    }
    throw err;
  }
}

/** Typed without picking a suggestion: take the best match, or fall back to the ZIP in the text. */
async function placeFromText(text: string): Promise<Place | null> {
  const best = await firstPlace(text);
  if (best) return best;
  const zip = zipFrom(text);
  const info = zip ? await api.zip(zip).catch(() => null) : null;
  return info && zip ? { label: text, zip, city: info.city, state: info.state, lat: info.lat, lon: info.lon } : null;
}

function signupError(err: unknown): string {
  if (err instanceof ApiError && err.code === 'email_taken')
    return 'That email already has an account. Sign in instead.';
  if (err instanceof ApiError && err.status === 422)
    return 'Check your email and use a password of at least 8 characters.';
  return err instanceof Error ? err.message : 'Could not create your account.';
}

export function Onboarding({ onSignedIn }: { onSignedIn: () => void }) {
  const [place, setPlace] = useState<Place | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const run = async (task: () => Promise<void>) => {
    setBusy(true);
    try {
      await task();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  const checkPlace = async (p: Place | null) => {
    if (!p) return setError('Pick your address from the list.');
    const problem = await covered(p);
    if (problem) return setError(problem);
    saveDraftAddress(p.label);
    saveDraftPlace(p);
    setError('');
    setPlace(p);
  };
  const choosePlace = (p: Place | null) => run(() => checkPlace(p));

  // Picked an address on the homepage? Go straight to the account step.
  // biome-ignore lint/correctness/useExhaustiveDependencies: run once on mount
  useEffect(() => {
    const draft = getDraftPlace();
    if (draft) void choosePlace(draft);
  }, []);

  const signUp = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!place) return;
    const form = new FormData(e.currentTarget);
    void run(async () => {
      try {
        const res = await api.signup({
          name: String(form.get('name')).trim(),
          email: String(form.get('email')).trim(),
          password: String(form.get('password')),
          zip: place.zip,
          location: { lat: place.lat, lon: place.lon },
        });
        setToken(res.token);
        onSignedIn();
      } catch (err) {
        setError(signupError(err));
      }
    });
  };

  return (
    <section className="onboard">
      <img className="stage-photo" src={shorePhoto} alt="" />
      <div className="onboard-card">
        <Brand />
        {place ? (
          <form className="step" onSubmit={signUp}>
            <h1>Create your account</h1>
            <button className="place" type="button" title="Change address" onClick={() => setPlace(null)}>
              <Icon name="pin" />
              <span>{place.label}</span>
              <small>Change</small>
            </button>
            <div className="fields">
              <label>
                Name
                <input name="name" autoComplete="name" required maxLength={80} />
              </label>
              <label>
                Email
                <input name="email" type="email" autoComplete="email" required />
              </label>
              <label>
                Password
                <input
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  required
                  placeholder="At least 8 characters"
                />
              </label>
            </div>
            <button className="button wide" type="submit" disabled={busy}>
              Create account
              <Icon name="arrow" />
            </button>
          </form>
        ) : (
          <div className="step">
            <h1>Where are you starting?</h1>
            <AddressSearch
              cta="Continue"
              initial={getDraftAddress()}
              placeholder="Start typing your address"
              nearby
              busy={busy}
              onPlace={choosePlace}
              onText={(text) => run(async () => checkPlace(await placeFromText(text)))}
            />
          </div>
        )}
        {error && (
          <p className="hint error" role="alert">
            {error}
          </p>
        )}
      </div>
    </section>
  );
}
