import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { fileURLToPath } from "url";
import { describe, expect, it } from "vitest";

// GAP-015: absolute clinical language in UI strings needs a source
const BANNED = [
  /\bdefinitely\b/i,
  /\bcertainly\b/i,
  /\bproves?\b/i,
  /\b100%\s*(accurate|correct|reliable)\b/i,
  /\brule[s]? out\b/i,
];

function srcFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) out.push(...srcFiles(p));
    else if (/\.(tsx|ts)$/.test(entry)) out.push(p);
  }
  return out;
}

describe("absolute-language audit", () => {
  it("no banned absolute claims in UI source", () => {
    const root = fileURLToPath(new URL("..", import.meta.url));
    const violations: string[] = [];
    for (const file of srcFiles(root)) {
      if (file.endsWith(".test.ts") || file.endsWith(".test.tsx")) continue;
      const text = readFileSync(file, "utf8");
      for (const re of BANNED) {
        const m = text.match(re);
        if (m) violations.push(`${file}: ${m[0]}`);
      }
    }
    expect(violations).toEqual([]);
  });
});
