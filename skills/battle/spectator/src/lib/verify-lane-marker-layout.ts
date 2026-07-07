const MARKER_SELECTOR = "[data-battle-marker-label],[data-battle-marker-icon]";

export function countMarkerOverlaps(root: ParentNode): number {
	let overlaps = 0;
	root.querySelectorAll("[data-lane-row]").forEach((row) => {
		const markers = [...row.querySelectorAll(MARKER_SELECTOR)];
		for (let i = 0; i < markers.length; i += 1) {
			for (let j = i + 1; j < markers.length; j += 1) {
				const a = markers[i].getBoundingClientRect();
				const b = markers[j].getBoundingClientRect();
				if (Math.abs(a.left - b.left) < 10 && Math.abs(a.top - b.top) < 14) overlaps += 1;
			}
		}
	});
	return overlaps;
}

export function warnMarkerOverlaps(root: ParentNode, context = "battle race viewport") {
	const overlaps = countMarkerOverlaps(root);
	if (overlaps > 0) console.warn(`[${context}] marker overlaps:`, overlaps);
	return overlaps;
}
