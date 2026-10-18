// Sections fade in as they scroll into view. Render with key={pathname} to re-arm per page.
import { useEffect } from 'react';

export function ScrollEffects() {
  useEffect(() => {
    const seen = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          e.target.classList.add('in');
          seen.unobserve(e.target);
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' },
    );
    for (const el of document.querySelectorAll('[data-reveal]')) seen.observe(el);
    return () => seen.disconnect();
  }, []);
  return null;
}
