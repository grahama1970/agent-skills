import { useEffect, useRef } from "react";

const API = "";

interface ActionDef {
	app: string;
	action: string;
	label: string;
	description: string;
	params?: Record<string, unknown>;
	tags?: string[];
}

const pendingRegistrations: Array<{ elementId: string; def: ActionDef }> = [];
const queuedRegistrationKeys = new Set<string>();
const flushedRegistrationKeys = new Set<string>();
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function registrationKey(elementId: string, def: ActionDef): string {
	return `${def.app}::${def.action}::${elementId}`;
}

function safeSerialize(value: unknown): string {
	try {
		return JSON.stringify(value);
	} catch {
		return JSON.stringify({ error: "unserializable-action-params" });
	}
}

function flushRegistrations() {
	if (pendingRegistrations.length === 0) return;
	const batch = pendingRegistrations.splice(0, 200);
	const docs = batch.map(({ elementId, def }) => ({
		_key: elementId,
		app: def.app,
		action: def.action,
		doc_type: "action_registration",
		element_id: elementId,
		problem: `${def.label}: ${def.description}`,
		solution: safeSerialize({ ui_action: def.action, params: def.params ?? {} }),
		label: def.label,
		description: def.description,
		tags: ["queryspec-action", def.app, `action:${def.action}`, ...(def.tags ?? [])],
		scope: def.app,
		registered_at: new Date().toISOString(),
	}));
	fetch(`${API}/api/memory/upsert`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ collection: "app_actions", documents: docs }),
	})
		.then(() => {
			for (const { elementId, def } of batch) {
				queuedRegistrationKeys.delete(registrationKey(elementId, def));
				flushedRegistrationKeys.add(registrationKey(elementId, def));
			}
		})
		.catch(() => {
			for (const { elementId, def } of batch) {
				queuedRegistrationKeys.delete(registrationKey(elementId, def));
			}
		})
		.finally(() => {
			flushTimer = null;
			if (pendingRegistrations.length > 0) {
				flushTimer = setTimeout(flushRegistrations, 100);
			}
		});
}

export function useRegisterAction(elementId: string, def: ActionDef) {
	const registeredRef = useRef(false);
	useEffect(() => {
		if (registeredRef.current) return;
		const key = registrationKey(elementId, def);
		if (flushedRegistrationKeys.has(key) || queuedRegistrationKeys.has(key)) {
			registeredRef.current = true;
			return;
		}
		registeredRef.current = true;
		pendingRegistrations.push({ elementId, def });
		queuedRegistrationKeys.add(key);
		if (flushTimer) clearTimeout(flushTimer);
		flushTimer = setTimeout(flushRegistrations, 500);
		return () => {
			registeredRef.current = true;
		};
	}, [elementId, def]);
}
