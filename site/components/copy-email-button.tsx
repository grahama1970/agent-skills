'use client';

import { type ReactNode, useState } from 'react';

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect width="14" height="14" x="8" y="8" rx="2" />
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
    </svg>
  );
}

type CopyEmailButtonProps = {
  email: string;
  children?: ReactNode;
  className?: string;
  qid?: string;
  qsAction?: string;
  title?: string;
  showStatus?: boolean;
};

export function CopyEmailButton({
  email,
  children,
  className = 'cv-copy-email',
  qid = 'resume:button:copy-email',
  qsAction = 'RESUME_COPY_EMAIL',
  title,
  showStatus = true,
}: CopyEmailButtonProps) {
  const [copied, setCopied] = useState(false);

  async function copyEmail() {
    try {
      await navigator.clipboard.writeText(email);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button
      type="button"
      className={className}
      onClick={copyEmail}
      data-qid={qid}
      data-qs-action={qsAction}
      title={title ?? `Copy ${email}`}
      aria-label={`Copy ${email}`}
    >
      {children ?? (
        <>
          <span>{email}</span>
          <CopyIcon />
        </>
      )}
      {showStatus && (
        <span className="cv-copy-email-status" aria-live="polite">
          {copied ? 'Copied' : 'Copy'}
        </span>
      )}
    </button>
  );
}
