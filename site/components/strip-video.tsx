'use client';

import { useEffect, useRef, useState } from 'react';

/** The dream-hero video. Autoplays muted + loops on real devices; falls back to
 *  the static poster only for the two constraints worth respecting: reduced
 *  motion (accessibility) and save-data (metered connections). Everything else —
 *  including touch devices — gets the clip, now that it's a lean ~1.1 MB H.264
 *  (a fresh-clone re-encode; the original was a 9.3 MB, ~14 Mbps file that
 *  stalled real buffering). Uses the native `autoplay` attribute plus a belt-
 *  and-suspenders play() call so it starts reliably without a fragile
 *  pointer-type gate. */
export function StripVideo() {
  const ref = useRef<HTMLVideoElement>(null);
  const [play, setPlay] = useState(false);

  // Defer the ~1 MB clip until the strip nears the viewport, so it never sits on
  // the initial-load critical path (the hero above it must paint fast). Honours
  // reduced-motion and save-data — those keep the static poster.
  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const saveData =
      (navigator as unknown as { connection?: { saveData?: boolean } }).connection
        ?.saveData ?? false;
    if (reduce || saveData) return;
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setPlay(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setPlay(true);
          io.disconnect();
        }
      },
      { rootMargin: '400px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (play) ref.current?.play?.().catch(() => {});
  }, [play]);

  return (
    <video
      ref={ref}
      className="strip-video"
      muted
      loop
      playsInline
      autoPlay={play}
      preload={play ? 'auto' : 'none'}
      poster="/dream/horus-embry-hero.webp"
    >
      {play && <source src="/dream/horus-embry.mp4" type="video/mp4" />}
    </video>
  );
}
