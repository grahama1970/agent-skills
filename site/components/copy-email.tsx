'use client';

import { useRef, useState } from 'react';

const EMAIL = 'graham@grahama.co';

/** Click copies the address and confirms with a toast; clipboard failure
 *  falls back to a normal mailto navigation. */
export function CopyEmail({ className }: { className?: string }) {
  const [toast, setToast] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const onClick = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    try {
      e.preventDefault();
      await navigator.clipboard.writeText(EMAIL);
      setToast(`Copied ${EMAIL} to clipboard`);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setToast(''), 2200);
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
        className={className}
      >
        Email {EMAIL}
      </a>
      <div
        role="status"
        aria-live="polite"
        className={`ui-toast${toast ? ' is-active' : ''}`}
      >
        {toast}
      </div>
    </>
  );
}
