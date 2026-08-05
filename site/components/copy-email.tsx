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

  const onMove = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left - rect.width / 2) * 0.15;
    const y = (e.clientY - rect.top - rect.height / 2) * 0.15;
    e.currentTarget.style.translate = `${x}px ${y}px`;
  };
  const onLeave = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.currentTarget.style.translate = '0px 0px';
  };

  return (
    <>
      <a
        href={`mailto:${EMAIL}`}
        onClick={onClick}
        onMouseMove={onMove}
        onMouseLeave={onLeave}
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
