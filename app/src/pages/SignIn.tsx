import { type FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { Brand } from '../components/SiteLayout.tsx';
import { ApiError, api } from '../lib/api.ts';
import { setToken } from '../lib/session.ts';

const PHOTO = 'https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=2200&q=80';

function message(err: unknown): string {
  if (err instanceof ApiError && err.code === 'invalid_credentials') return 'Wrong email or password.';
  if (err instanceof ApiError && err.code === 'too_many_attempts') return 'Too many attempts. Try again in 15 minutes.';
  return err instanceof Error ? err.message : 'Could not sign in.';
}

export default function SignIn() {
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError('');
    try {
      const res = await api.login(String(form.get('email')).trim(), String(form.get('password')));
      setToken(res.token);
      navigate('/app');
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <title>Sign in · Harbor</title>
      <img className="stage-photo" src={PHOTO} alt="" />
      <form className="auth-card" onSubmit={onSubmit}>
        <Brand />
        <h1>Sign in</h1>
        <label htmlFor="email">Email</label>
        <input id="email" name="email" type="email" autoComplete="email" required />
        <label htmlFor="password">Password</label>
        <input id="password" name="password" type="password" autoComplete="current-password" required />
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        <button className="button" type="submit" disabled={busy}>
          Continue
        </button>
        <p>
          New to Harbor? <Link to="/app">Create an account</Link>
        </p>
      </form>
    </main>
  );
}
