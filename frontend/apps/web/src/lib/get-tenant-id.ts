import type { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";

export class MissingTenantError extends Error {
	constructor() {
		super("Session expired: tenant ID unavailable. Please log in again.");
		this.name = "MissingTenantError";
	}
}

/**
 * Returns the tenant ID from localStorage.
 * If absent or empty, redirects to /login and throws MissingTenantError.
 * Never falls back to a hardcoded UUID.
 */
export function getTenantIdOrRedirect(router?: AppRouterInstance): string {
	if (typeof window === "undefined") {
		throw new MissingTenantError();
	}
	const tid = localStorage.getItem("aegis_tenant_id");
	if (!tid) {
		if (router) {
			router.push("/login?reason=session_expired");
		} else {
			window.location.href = "/login?reason=session_expired";
		}
		throw new MissingTenantError();
	}
	return tid;
}
