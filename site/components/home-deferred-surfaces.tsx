'use client';

import {
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type RefObject,
} from 'react';
import type { DreamPhase } from './dream-stepper';

type ReceiptTicketProps = {
  id: string;
  title: string;
  callout: string;
  proves: string;
  doesNotProve: string;
  body: string;
  caption: string;
};

function useNearViewport(ref: RefObject<HTMLElement | null>, rootMargin = '900px') {
  const [near, setNear] = useState(false);

  useEffect(() => {
    if (near) return;
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setNear(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [near, ref, rootMargin]);

  return near;
}

export function DeferredCapabilitySearch() {
  const ref = useRef<HTMLDivElement>(null);
  const near = useNearViewport(ref);
  const [Surface, setSurface] = useState<ComponentType | null>(null);

  useEffect(() => {
    if (!near || Surface) return;
    import('./capability-search').then((mod) => {
      setSurface(() => mod.CapabilitySearch);
    });
  }, [near, Surface]);

  return <div ref={ref}>{Surface ? <Surface /> : null}</div>;
}

export function DeferredDreamStepper({ phases }: { phases: DreamPhase[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const near = useNearViewport(ref);
  const [Surface, setSurface] =
    useState<ComponentType<{ phases: DreamPhase[] }> | null>(null);

  useEffect(() => {
    if (!near || Surface) return;
    import('./dream-stepper').then((mod) => {
      setSurface(() => mod.DreamStepper);
    });
  }, [near, Surface]);

  return (
    <div ref={ref} className="deferred-surface deferred-surface--dream">
      {Surface ? <Surface phases={phases} /> : null}
    </div>
  );
}

export function DeferredReceiptTicket(props: ReceiptTicketProps) {
  const ref = useRef<HTMLElement>(null);
  const near = useNearViewport(ref, '700px');
  const [Surface, setSurface] =
    useState<ComponentType<ReceiptTicketProps> | null>(null);

  useEffect(() => {
    if (!near || Surface) return;
    import('./receipt-ticket').then((mod) => {
      setSurface(() => mod.ReceiptTicket);
    });
  }, [near, Surface]);

  if (Surface) return <Surface {...props} />;

  return (
    <article ref={ref} className="ticket">
      <h3>{props.title}</h3>
      <p className="callout">{props.callout}</p>
      <p className="proves">{props.proves}</p>
      <p className="does-not-prove">{props.doesNotProve}</p>
      <p className="human">
        {props.caption}. The judgment, proof boundary, and raw payload stay
        together; the summary is never the only evidence.
      </p>
      <p className="foot">{props.caption}</p>
    </article>
  );
}

export function DeferredKeyboardNav() {
  const [Surface, setSurface] = useState<ComponentType | null>(null);

  useEffect(() => {
    const load = () => {
      import('./keyboard-nav').then((mod) => {
        setSurface(() => mod.KeyboardNav);
      });
    };
    const idle = (
      window as Window & {
        requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
      }
    ).requestIdleCallback;
    if (idle) {
      const id = idle(load, { timeout: 2500 });
      return () => {
        const cancel = (
          window as Window & { cancelIdleCallback?: (id: number) => void }
        ).cancelIdleCallback;
        if (cancel) cancel(id);
      };
    }
    const timeout = window.setTimeout(load, 1200);
    return () => window.clearTimeout(timeout);
  }, []);

  return Surface ? <Surface /> : null;
}
