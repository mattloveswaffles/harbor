// CSS custom properties in style objects, e.g. style={{ '--d': '.1s' }} for the reveal delays.
import 'react';

declare module 'react' {
  interface CSSProperties {
    [property: `--${string}`]: string | number;
  }
}
