import { Link } from 'react-router';

export default function NotFound() {
  return (
    <main className="container not-found">
      <title>Not found · Harbor</title>
      <h1>Page not found.</h1>
      <p>
        <Link className="button" to="/">
          Back home
        </Link>
      </p>
    </main>
  );
}
