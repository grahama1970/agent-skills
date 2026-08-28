import { useState, useEffect, useCallback } from "react";

interface UseCardNavigationOptions {
  itemCount: number;
  initialIndex?: number;
  enableNumberKeys?: boolean;
  loop?: boolean;
}

export function useCardNavigation({
  itemCount,
  initialIndex = 0,
  enableNumberKeys = true,
  loop = false,
}: UseCardNavigationOptions) {
  const [activeIndex, setActiveIndex] = useState<number>(initialIndex);

  const navigate = useCallback(
    (direction: "next" | "prev") => {
      if (itemCount === 0) return;
      setActiveIndex((prev) => {
        if (direction === "next") {
          if (prev < itemCount - 1) return prev + 1;
          return loop ? 0 : prev;
        }
        if (prev > 0) return prev - 1;
        return loop ? itemCount - 1 : prev;
      });
    },
    [itemCount, loop],
  );

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }
      if (event.key === "ArrowDown" || event.key === "j") {
        event.preventDefault();
        navigate("next");
      } else if (event.key === "ArrowUp" || event.key === "k") {
        event.preventDefault();
        navigate("prev");
      } else if (enableNumberKeys && /^[1-9]$/.test(event.key)) {
        const targetIndex = parseInt(event.key, 10) - 1;
        if (targetIndex < itemCount) {
          event.preventDefault();
          setActiveIndex(targetIndex);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [itemCount, navigate, enableNumberKeys]);

  return {
    activeIndex,
    setActiveIndex,
    navigateNext: () => navigate("next"),
    navigatePrev: () => navigate("prev"),
  };
}
