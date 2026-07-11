/** Humanized claim-boundary copy for music schedule chrome. Never claims speaker output. */

const MAY: Record<string, string> = {
	assets_promoted: "Promoted MIDI/OGG assets exist under /battle-audio/promoted/v1/.",
	receipt_authorized_schedule_emitted: "Schedule entries cite authorizing Battle receipts.",
	version_hashes_recorded: "Immutable content hashes are recorded for assets and receipts.",
};

const MUST_NOT: Record<string, string> = {
	audio_played: "Decode/arm is not proof that audio played for a listener.",
	speaker_output: "This surface does not prove speaker or headphone output.",
	death: "Death music requires a confirmed terminal receipt.",
	victory: "Victory music requires Judge EXPLOIT_SUCCESS only.",
	arena_transition: "Next-arena requires accepted/committed transition evidence.",
	exploit_success: "Music never proves exploit success.",
	blue_outcome: "Music never proves Blue outcomes.",
	judge_success: "Music never proves Judge success.",
};

export function musicClaimMayCopy(key: string): { title: string; detail: string } {
	return {
		title: key,
		detail: MAY[key] ?? "Allowed only as stated by the normalized music fixture.",
	};
}

export function musicClaimMustNotCopy(key: string): { title: string; detail: string } {
	return {
		title: key,
		detail: MUST_NOT[key] ?? "Must not be inferred from music state alone.",
	};
}
