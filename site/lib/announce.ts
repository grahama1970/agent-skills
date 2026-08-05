/**
 * Global accessibility live-region announcer for assistive technologies.
 * 'polite' waits for a pause (drawer/theme changes); 'assertive' interrupts
 * (clipboard copies). Containers are auto-injected on first use.
 */
export function announce(
  message: string,
  politeness: 'polite' | 'assertive' = 'polite',
) {
  const id =
    politeness === 'assertive'
      ? 'a11y-announcer-assertive'
      : 'a11y-announcer-polite';
  let region = document.getElementById(id);
  if (!region) {
    region = document.createElement('div');
    region.id = id;
    region.className = 'sr-only';
    region.setAttribute('aria-live', politeness);
    region.setAttribute('aria-atomic', 'true');
    document.body.appendChild(region);
  }
  region.textContent = '';
  setTimeout(() => {
    if (region) region.textContent = message;
  }, 50);
}
