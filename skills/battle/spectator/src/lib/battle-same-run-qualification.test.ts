import { expect, it } from "vitest";
import { battleReceiptReplayFixtureKey, battleReceiptReplayFixtureUrl } from "./battle-receipt-replay";

it("registers the same-run qualification receipt route", () => {
	const hash = "#battle/receipt?engine=pixi&fixture=battle-004-same-run-qualification";
	expect(battleReceiptReplayFixtureKey(hash)).toBe("battle-004-same-run-qualification");
	expect(battleReceiptReplayFixtureUrl(hash)).toBe(
		"/battle-fixtures/battle-004-same-run-qualification/battle.normalized_ux_fixture.json",
	);
});
