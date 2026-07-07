import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

export function pct(x: number) {
	return `${Math.max(0, Math.min(100, x))}%`;
}

export function trackPct(x: number) {
	const cardGutter = 24;
	const trackSpan = 72;
	return cardGutter + (Math.max(0, Math.min(100, x)) / 100) * trackSpan;
}

export function formatClock(ms: number) {
	const total = Math.floor(ms / 1000);
	const min = Math.floor(total / 60)
		.toString()
		.padStart(2, "0");
	const sec = (total % 60).toString().padStart(2, "0");
	return `${min}:${sec}`;
}
