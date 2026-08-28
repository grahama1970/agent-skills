import { useEffect, useRef } from "react";

interface AutoScrollOptions extends ScrollIntoViewOptions {
  /** Prevent page-level jumping by restricting scrolling strictly within container */
  containToParent?: boolean;
}

export function useAutoScroll<T extends HTMLElement>(
  activeIndex: number,
  options: AutoScrollOptions = {},
) {
  const {
    behavior = "smooth",
    block = "nearest",
    inline = "nearest",
    containToParent = true,
  } = options;

  const itemRefs = useRef<(T | null)[]>([]);

  useEffect(() => {
    const activeEl = itemRefs.current[activeIndex];
    if (!activeEl) return;

    if (containToParent && activeEl.parentElement) {
      const parent = activeEl.parentElement;
      const parentRect = parent.getBoundingClientRect();
      const elRect = activeEl.getBoundingClientRect();
      const isAbove = elRect.top < parentRect.top;
      const isBelow = elRect.bottom > parentRect.bottom;
      if (isAbove || isBelow) {
        activeEl.scrollIntoView({ behavior, block, inline });
      }
    } else {
      activeEl.scrollIntoView({ behavior, block, inline });
    }
  }, [activeIndex, behavior, block, inline, containToParent]);

  return itemRefs;
}
