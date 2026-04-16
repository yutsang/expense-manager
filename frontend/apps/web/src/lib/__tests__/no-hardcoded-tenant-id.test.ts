import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, test } from "vitest";

const FORBIDDEN = "00000000-0000-0000-0000-000000000001";
const SRC_ROOT = path.resolve(__dirname, "../../..");

function scanDir(dir: string): string[] {
	return readdirSync(dir).flatMap((entry) => {
		const full = path.join(dir, entry);
		if (
			statSync(full).isDirectory() &&
			entry !== "node_modules" &&
			entry !== ".next" &&
			entry !== "__tests__"
		) {
			return scanDir(full);
		}
		if (
			/\.(ts|tsx)$/.test(entry) &&
			!entry.endsWith(".test.ts") &&
			!entry.endsWith(".test.tsx") &&
			!entry.endsWith(".spec.ts") &&
			!entry.endsWith(".spec.tsx")
		) {
			return [full];
		}
		return [];
	});
}

describe("hardcoded tenant UUID regression guard", () => {
	test("hardcoded tenant UUID must not appear in any TypeScript source file", () => {
		const violations = scanDir(SRC_ROOT).filter((file) =>
			readFileSync(file, "utf-8").includes(FORBIDDEN),
		);
		expect(violations).toEqual([]);
	});
});
