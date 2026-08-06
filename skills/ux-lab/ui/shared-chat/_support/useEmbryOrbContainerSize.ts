import { useEffect, useRef, useState } from "react";

/**
 * Container-driven orb size (D3 layout rule: ResizeObserver, not hardcoded pixels).
 */
export function useEmbryOrbContainerSize(
	fallback = 96,
	opts?: { min?: number; max?: number },
): { ref: React.RefObject<HTMLDivElement | null>; size: number } {
	const min = opts?.min ?? 72;
	const max = opts?.max ?? 128;
	const ref = useRef<HTMLDivElement>(null);
	const [size, setSize] = useState(fallback);

	useEffect(() => {
		const element = ref.current;
		if (!element || typeof ResizeObserver === "undefined") return;

		const measure = (): void => {
			const rect = element.getBoundingClientRect();
			const next = Math.round(Math.min(max, Math.max(min, Math.min(rect.width, rect.height) || fallback)));
			setSize((prev) => (prev === next ? prev : next));
		};

		measure();
		const observer = new ResizeObserver(() => measure());
		observer.observe(element);
		return () => observer.disconnect();
	}, [fallback, max, min]);

	return { ref, size };
}
