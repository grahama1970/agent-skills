/** Fail-closed score formatting for receipt-backed surfaces. */
export function formatReceiptScore(value: number | undefined): string {
	if (typeof value === "number" && Number.isFinite(value)) {
		return value.toFixed(value % 1 === 0 ? 0 : 1);
	}
	return "not emitted";
}

export function formatReceiptCount(value: number | undefined): string {
	if (typeof value === "number" && Number.isFinite(value)) {
		return String(value);
	}
	return "not emitted";
}
