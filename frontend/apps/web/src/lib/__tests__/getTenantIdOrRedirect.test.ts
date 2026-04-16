import { beforeEach, describe, expect, test, vi } from "vitest";
import { MissingTenantError, getTenantIdOrRedirect } from "../get-tenant-id";

describe("getTenantIdOrRedirect", () => {
	beforeEach(() => {
		localStorage.clear();
	});

	test("returns tenant ID when aegis_tenant_id is in localStorage", () => {
		const mockRouter = { push: vi.fn() } as unknown as import("next/dist/shared/lib/app-router-context.shared-runtime").AppRouterInstance;
		localStorage.setItem("aegis_tenant_id", "real-tenant-uuid");

		const result = getTenantIdOrRedirect(mockRouter);

		expect(result).toBe("real-tenant-uuid");
		expect(mockRouter.push).not.toHaveBeenCalled();
	});

	test("throws MissingTenantError and redirects when aegis_tenant_id is absent", () => {
		const mockRouter = { push: vi.fn() } as unknown as import("next/dist/shared/lib/app-router-context.shared-runtime").AppRouterInstance;

		expect(() => getTenantIdOrRedirect(mockRouter)).toThrow(MissingTenantError);
		expect(mockRouter.push).toHaveBeenCalledWith(
			"/login?reason=session_expired",
		);
	});

	test("throws MissingTenantError and redirects when aegis_tenant_id is empty string", () => {
		const mockRouter = { push: vi.fn() } as unknown as import("next/dist/shared/lib/app-router-context.shared-runtime").AppRouterInstance;
		localStorage.setItem("aegis_tenant_id", "");

		expect(() => getTenantIdOrRedirect(mockRouter)).toThrow(MissingTenantError);
		expect(mockRouter.push).toHaveBeenCalledWith(
			"/login?reason=session_expired",
		);
	});

	test("falls back to window.location.href redirect when no router provided", () => {
		let capturedHref = "";
		const locationMock = {
			get href() {
				return capturedHref;
			},
			set href(v: string) {
				capturedHref = v;
			},
		};
		Object.defineProperty(window, "location", {
			configurable: true,
			get: () => locationMock,
		});

		expect(() => getTenantIdOrRedirect()).toThrow(MissingTenantError);
		expect(capturedHref).toBe("/login?reason=session_expired");
	});

	test("never returns the hardcoded fallback UUID", () => {
		const mockRouter = { push: vi.fn() } as unknown as import("next/dist/shared/lib/app-router-context.shared-runtime").AppRouterInstance;
		localStorage.setItem("aegis_tenant_id", "real-uuid");

		const result = getTenantIdOrRedirect(mockRouter);

		expect(result).not.toBe("00000000-0000-0000-0000-000000000001");
	});
});
