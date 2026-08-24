'use client';

import { useEffect, useRef, useState } from 'react';
import type { MouseEvent, ReactNode } from 'react';

type CalendlyApi = {
  initInlineWidget: (options: { url: string; parentElement: HTMLElement; resize?: boolean }) => void;
  initPopupWidget: (options: {
    url: string;
    parentElement?: HTMLElement;
    prefill?: Record<string, unknown>;
    utm?: {
      utmSource?: string;
      utmMedium?: string;
      utmCampaign?: string;
      utmContent?: string;
      utmTerm?: string;
    };
  }) => void;
};

declare global {
  interface Window {
    Calendly?: CalendlyApi;
  }
}

let calendlyScript: Promise<void> | null = null;

function loadCalendly() {
  if (typeof window === 'undefined') return Promise.resolve();
  if (window.Calendly) return Promise.resolve();
  if (calendlyScript) return calendlyScript;

  calendlyScript = new Promise<void>((resolve, reject) => {
    if (!document.querySelector('link[data-calendly-widget-css]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = 'https://assets.calendly.com/assets/external/widget.css';
      link.dataset.calendlyWidgetCss = 'true';
      document.head.appendChild(link);
    }

    const existing = document.querySelector<HTMLScriptElement>('script[data-calendly-widget-js]');
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', reject, { once: true });
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://assets.calendly.com/assets/external/widget.js';
    script.async = true;
    script.dataset.calendlyWidgetJs = 'true';
    script.addEventListener('load', () => resolve(), { once: true });
    script.addEventListener('error', reject, { once: true });
    document.head.appendChild(script);
  });

  return calendlyScript;
}

function isCalendlyEvent(event: MessageEvent) {
  return event.origin === 'https://calendly.com'
    && typeof event.data?.event === 'string'
    && event.data.event.startsWith('calendly.');
}

export function CalendlyInlineWidget({ url }: { url: string }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'scheduled' | 'unavailable'>('loading');

  useEffect(() => {
    let canceled = false;
    loadCalendly()
      .then(() => {
        if (canceled || !parentRef.current || !window.Calendly) return;
        parentRef.current.innerHTML = '';
        window.Calendly.initInlineWidget({
          url,
          parentElement: parentRef.current,
          resize: true,
        });
        setStatus('ready');
      })
      .catch(() => {
        if (!canceled) setStatus('unavailable');
      });

    const onMessage = (event: MessageEvent) => {
      if (isCalendlyEvent(event) && event.data.event === 'calendly.event_scheduled') {
        setStatus('scheduled');
      }
    };
    window.addEventListener('message', onMessage);
    return () => {
      canceled = true;
      window.removeEventListener('message', onMessage);
    };
  }, [url]);

  return (
    <div className="calendly-panel" data-qid="contact:calendly:inline">
      <div className="calendly-panel-head">
        <p className="lab">Calendly</p>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          data-qid="contact:calendly:open"
          data-qs-action="CONTACT_OPEN_CALENDLY"
          title="Open Calendly in a new tab"
        >
          Open in a new tab ↗
        </a>
      </div>
      <div ref={parentRef} className="calendly-inline-frame" aria-busy={status === 'loading'} />
      {status === 'scheduled' ? <p className="calendly-status">Booked.</p> : null}
      {status === 'unavailable' ? (
        <p className="calendly-status">
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            data-qid="contact:calendly:fallback"
            data-qs-action="CONTACT_OPEN_CALENDLY_FALLBACK"
            title="Open Calendly in a new tab"
          >
            Open Calendly
          </a>.
        </p>
      ) : null}
    </div>
  );
}

export function CalendlyPopupLink({
  url,
  className,
  qid,
  children = 'Book a 30-minute meeting',
  showArrow = true,
  title = 'Book a 30-minute meeting',
  utmSource = 'grahama.co',
  utmMedium = 'direct_site',
}: {
  url: string;
  className?: string;
  qid: string;
  children?: ReactNode;
  showArrow?: boolean;
  title?: string;
  utmSource?: string;
  utmMedium?: string;
}) {
  const openFallback = () => {
    const opened = window.open(url, '_blank', 'noopener,noreferrer');
    if (!opened) window.location.href = url;
  };

  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (typeof window === 'undefined') return;
    event.preventDefault();
    loadCalendly()
      .then(() => {
        if (window.Calendly) {
          window.Calendly.initPopupWidget({
            url,
            parentElement: document.body,
            prefill: {},
            utm: {
              utmSource,
              utmMedium,
            },
          });
        } else {
          openFallback();
        }
      })
      .catch(() => {
        openFallback();
      });
  };

  return (
    <a
      className={className}
      href={url}
      onClick={onClick}
      data-qid={qid}
      data-qs-action="OPEN_CALENDLY_POPUP"
      title={title}
    >
      {children}
      {showArrow ? <> <span className="arrow">↗</span></> : null}
    </a>
  );
}
