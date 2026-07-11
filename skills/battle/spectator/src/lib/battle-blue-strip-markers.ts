export type BlueStripMarker = {
	id: string;
	label: string;
	left: number;
	clock: string;
	detailLabel?: string;
};

/** Co-located patches (same x) stack into one chip so labels do not collide. */
export function clusterBlueMarkers(
	markers: BlueStripMarker[],
	threshold = 3,
): Array<BlueStripMarker & { stacked: number; title: string }> {
	const sorted = [...markers].sort((a, b) => a.left - b.left);
	const clusters: Array<BlueStripMarker & { stacked: number; title: string }> = [];
	for (const marker of sorted) {
		const prev = clusters[clusters.length - 1];
		if (prev && Math.abs(prev.left - marker.left) <= threshold) {
			prev.stacked += 1;
			prev.title = `${prev.title} · ${marker.label} ${marker.clock}`;
			const base = prev.label.split(" · ")[0] ?? prev.label;
			prev.label = `${base} · +${prev.stacked - 1}`;
			continue;
		}
		clusters.push({
			...marker,
			stacked: 1,
			title: marker.detailLabel ?? `${marker.label} · ${marker.clock}`,
		});
	}
	return clusters;
}
