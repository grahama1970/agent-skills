'use client';

import { useRef, useState } from 'react';
import { announce } from '@/lib/announce';

const EMAIL = 'graham@grahama.co';

/** Primary contact CTA. Click copies the address; the button itself
 *  confirms, plus a toast and an assertive announcement. Clipboard
 *  failure falls back to a normal mailto navigation. */
export function CopyEmail() {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const onClick = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    try {
      e.preventDefault();
      await navigator.clipboard.writeText(EMAIL);
      setCopied(true);
      announce(`Copied email ${EMAIL} to clipboard`, 'assertive');
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2200);
    } catch {
      window.location.href = `mailto:${EMAIL}`;
    }
  };

  return (
    <>
      <a
        href={`mailto:${EMAIL}`}
        onClick={onClick}
        data-qid="contact:action:email"
        data-qs-action="CONTACT_EMAIL"
        title={`Copy ${EMAIL} to clipboard`}
        className={`cta-button${copied ? ' is-copied' : ''}`}
      >
        <span className="cta-label">
          {copied ? 'Copied to clipboard' : `Email ${EMAIL}`}
        </span>
        <span aria-hidden="true" className="cta-arrow">
          {copied ? '✓' : '→'}
        </span>
      </a>
      <div className="machine mt-3 text-mute">
        click copies the address · or use the mail link in the header
      </div>
      <div
        role="status"
        aria-live="polite"
        className={`ui-toast${copied ? ' is-active' : ''}`}
      >
        {copied ? `Copied ${EMAIL} to clipboard` : ''}
      </div>
    </>
  );
}
