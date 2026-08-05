/** Splits text into per-word spans with staggered rise-in delays. */
export function Kinetic({
  text,
  startDelay = 0,
  dim = false,
}: {
  text: string;
  startDelay?: number;
  dim?: boolean;
}) {
  return (
    <>
      {text.split(' ').map((word, i) => (
        <span key={`${word}-${i}`} className="kinetic-word">
          <span
            className={dim ? 'text-mute' : undefined}
            style={{ ['--d' as string]: `${startDelay + i * 0.07}s` }}
          >
            {word}
          </span>{' '}
        </span>
      ))}
    </>
  );
}
