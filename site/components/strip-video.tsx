'use client';

import { useEffect, useRef, useState } from 'react';

/** The dream-hero video. Renders the poster keyframe by default and only loads
 *  + plays the clip on fine-pointer devices with motion allowed and no save-data
 *  — so phones, reduced-motion, and metered connections never fetch the ~9 MB
 *  mp4. Degrades to the exact static frame everywhere else. */
export function StripVideo() {
  const ref = useRef<HTMLVideoElement>(null);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const fine = window.matchMedia('(pointer: fine)').matches;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const saveData =
      (navigator as unknown as { connection?: { saveData?: boolean } }).connection
        ?.saveData ?? false;
    if (fine && !reduce && !saveData) setEnabled(true);
  }, []);

  useEffect(() => {
    if (enabled && ref.current) {
      ref.current.load();
      ref.current.play().catch(() => {});
    }
  }, [enabled]);

  return (
    <video
      ref={ref}
      className="strip-video"
      muted
      loop
      playsInline
      preload="none"
      poster="/dream/horus-embry-hero.webp"
    >
      {enabled && <source src="/dream/horus-embry.mp4" type="video/mp4" />}
    </video>
  );
}
