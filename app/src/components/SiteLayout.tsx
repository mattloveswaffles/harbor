// Marketing layout: announcement bar, header, page, footer.
import { Link, NavLink, Outlet, ScrollRestoration, useLocation } from 'react-router';
import { mark } from '../lib/assets.ts';
import { ScrollEffects } from './ScrollEffects.tsx';

const DOCS = 'https://github.com/mattloveswaffles/harbor/blob/main/docs';

export function Brand() {
  return (
    <Link className="brand" to="/">
      <img src={mark} alt="" />
      harbor
    </Link>
  );
}

export function SiteLayout() {
  const { pathname } = useLocation();
  return (
    <>
      <div className="announce">
        <div className="container">
          Atlantic hurricane season runs June 1 to November 30.
          <Link to="/app">
            Get your plan <span aria-hidden="true">→</span>
          </Link>
        </div>
      </div>
      <header className="site-header">
        <div className="container">
          <Brand />
          <nav className="nav" aria-label="Main">
            <NavLink to="/how-it-works">How it works</NavLink>
            <NavLink to="/impact">Impact</NavLink>
          </nav>
          <div className="header-actions">
            <Link className="button ghost small" to="/signin">
              Sign in
            </Link>
            <Link className="button small" to="/app">
              Get my plan
            </Link>
          </div>
        </div>
      </header>
      <Outlet />
      <footer className="site-footer">
        <div className="container">
          <div className="footer-row">
            <Brand />
            <nav className="footer-links">
              <Link to="/how-it-works">How it works</Link>
              <Link to="/impact">Impact</Link>
              <a href={`${DOCS}/Harbor.pptx`}>Pitch deck</a>
              <a href={`${DOCS}/research.md`}>Research</a>
            </nav>
          </div>
        </div>
      </footer>
      <ScrollEffects key={pathname} />
      <ScrollRestoration />
    </>
  );
}
