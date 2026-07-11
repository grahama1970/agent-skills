import {
	battleLiveTransportContractCompanionUrl,
	battleLiveTransportContractUrl,
	isRegisteredLiveTransportBattle,
	type BattleLiveTransportBattleId,
} from "./battle-live-transport-contract-registry";
import type {
	BattleLiveTransportContractLoadError,
	BattleLiveTransportContractV1,
	BattleLiveTransportContractViewModel,
} from "./battle-live-transport-contract-types";
import { validateLiveTransportContract } from "./battle-live-transport-contract-validator";
import { loadBattleRaceFixture } from "./battle-view-fixture-loader";
import type { BattleNormalizedUxFixture } from "./battle-types";

function fail(error: BattleLiveTransportContractLoadError): { ok: false; error: BattleLiveTransportContractLoadError } {
	return { ok: false, error };
}

export function liveTransportContractViewModel(
	contract: BattleLiveTransportContractV1,
): BattleLiveTransportContractViewModel {
	return {
		battleId: contract.battle_id,
		runId: contract.run_id,
		status: contract.status,
		live: "contract_only",
		mocked: false,
		transportKind: "sse",
		sseEndpoint: contract.transport.endpoint,
		snapshotEndpoint: contract.initial_snapshot.endpoint,
		contentType: contract.transport.content_type,
		geneticEventTypes: contract.event_stream.genetic_event_types_when_live,
		geneticEventCount: contract.event_stream.genetic_event_types_when_live.length,
		mayClaim: contract.claim_boundary.may_claim,
		mustNotClaim: contract.claim_boundary.must_not_claim,
		reconnectHeader: contract.reconnect.last_event_id_header,
		gapResponse: contract.gap_semantics.gap_response,
		route: contract.frontend_handoff.route,
		stopCondition: contract.frontend_handoff.stop_condition ?? "",
		sseClientArmed: true,
		sseClientConnected: false,
		endpointExecutionClaimed: false,
	};
}

export async function loadBattleLiveTransportContract(
	battleId: string,
): Promise<
	| {
			ok: true;
			contract: BattleLiveTransportContractV1;
			companion: BattleNormalizedUxFixture;
			viewModel: BattleLiveTransportContractViewModel;
	  }
	| { ok: false; error: BattleLiveTransportContractLoadError }
> {
	if (!isRegisteredLiveTransportBattle(battleId)) {
		return fail({
			code: "UNSUPPORTED_BATTLE",
			title: "UNSUPPORTED BATTLE",
			detail: `Live transport contract for battle "${battleId}" is not registered.`,
		});
	}
	const key = battleId as BattleLiveTransportBattleId;
	const url = battleLiveTransportContractUrl(key);
	try {
		const response = await fetch(url);
		if (!response.ok) {
			return fail({
				code: "CONTRACT_UNAVAILABLE",
				title: "CONTRACT UNAVAILABLE",
				detail: `Failed to fetch ${url} (${response.status}).`,
			});
		}
		const validated = validateLiveTransportContract(await response.json());
		if (!validated.ok) return validated;

		const companionResult = await loadBattleRaceFixture(battleLiveTransportContractCompanionUrl(key));
		if (!companionResult.ok) {
			return fail({
				code: "CONTRACT_UNAVAILABLE",
				title: "CONTRACT UNAVAILABLE",
				detail: `Companion race fixture unavailable: ${companionResult.error.detail}`,
			});
		}

		return {
			ok: true,
			contract: validated.contract,
			companion: companionResult.fixture,
			viewModel: liveTransportContractViewModel(validated.contract),
		};
	} catch (error) {
		return fail({
			code: "CONTRACT_UNAVAILABLE",
			title: "CONTRACT UNAVAILABLE",
			detail: error instanceof Error ? error.message : `Failed to fetch ${url}.`,
		});
	}
}
