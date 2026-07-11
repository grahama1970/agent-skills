import {
	battleMusicFixtureId,
	battleMusicFixtureUrl,
} from "./battle-music-registry";
import {
	buildMusicScheduleViewModel,
	validateNormalizedMusicFixture,
	type BattleNormalizedMusicFixture,
	type MusicFixtureLoadError,
	type MusicScheduleViewModel,
} from "./battle-normalized-music-fixture";

export type MusicLoadResult =
	| { ok: true; fixture: BattleNormalizedMusicFixture; viewModel: MusicScheduleViewModel }
	| { ok: false; error: MusicFixtureLoadError };

export async function loadBattleMusicFixture(hash: string): Promise<MusicLoadResult> {
	const id = battleMusicFixtureId(hash);
	const url = battleMusicFixtureUrl(hash);
	if (!id || !url) {
		return { ok: false, error: { code: "unknown_fixture", detail: "fixture not registered for #battle/music" } };
	}
	let response: Response;
	try {
		response = await fetch(url);
	} catch (error) {
		return { ok: false, error: { code: "fetch_failed", detail: String(error) } };
	}
	if (!response.ok) {
		return { ok: false, error: { code: "fetch_failed", detail: `HTTP ${response.status} for ${url}` } };
	}
	const raw = (await response.json()) as unknown;
	const invalid = validateNormalizedMusicFixture(raw);
	if (invalid) return { ok: false, error: invalid };
	const fixture = raw as BattleNormalizedMusicFixture;
	return { ok: true, fixture, viewModel: buildMusicScheduleViewModel(fixture) };
}
