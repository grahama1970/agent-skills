import { describe, expect, it } from "vitest";
import { musicClaimMayCopy, musicClaimMustNotCopy } from "./battle-music-claim-copy";

describe("battle music claim copy", () => {
	it("never frames decode as speaker proof", () => {
		expect(musicClaimMustNotCopy("speaker_output").detail).toMatch(/speaker|headphone/i);
		expect(musicClaimMustNotCopy("audio_played").detail).toMatch(/not proof/i);
		expect(musicClaimMayCopy("assets_promoted").detail).toMatch(/promoted/i);
	});
});
