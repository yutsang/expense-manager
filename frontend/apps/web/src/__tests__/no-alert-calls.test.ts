/**
 * Tests for Issue #5: No alert() calls in web app pages.
 *
 * Scans all page source files under (app)/ for raw `alert(` calls
 * to ensure they have been replaced with toast notifications.
 * Mobile `Alert.alert` (React Native) is excluded from this check.
 */
import { describe, expect, it } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";

function getPageFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...getPageFiles(fullPath));
    } else if (entry.name.endsWith(".tsx") || entry.name.endsWith(".ts")) {
      files.push(fullPath);
    }
  }
  return files;
}

describe("no alert() calls in web app pages", () => {
  const appDir = path.resolve(__dirname, "../app/(app)");
  const pages = getPageFiles(appDir);

  it("should have found page files to scan", () => {
    expect(pages.length).toBeGreaterThan(0);
  });

  for (const filePath of pages) {
    const relativePath = path.relative(path.resolve(__dirname, ".."), filePath);

    it(`${relativePath} should not contain alert() calls`, () => {
      const content = fs.readFileSync(filePath, "utf-8");
      // Match bare `alert(` but not `Alert.alert(` (React Native) or `useAlert` or `alertDialog`
      const alertPattern = /(?<![.\w])alert\s*\(/g;
      const matches = content.match(alertPattern);
      expect(
        matches,
        `Found ${matches?.length ?? 0} alert() call(s) in ${relativePath}`,
      ).toBeNull();
    });
  }
});

describe("toast utility exists", () => {
  it("should export a showToast function from lib/toast", async () => {
    const toastModule = await import("@/lib/toast");
    expect(toastModule.showToast).toBeDefined();
    expect(typeof toastModule.showToast).toBe("function");
  });
});
