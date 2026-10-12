import { describe, expect, it } from "vitest";
import { citedNumbers, linkifyCitations } from "@/lib/citations";

describe("linkifyCitations", () => {
  it("turns single and adjacent markers into links", () => {
    expect(linkifyCitations("Water boils at 100°C [1]. See also [2][3].")).toBe(
      "Water boils at 100°C [1](#cite-1). See also [2](#cite-2)[3](#cite-3).",
    );
  });

  it("expands comma lists and ranges", () => {
    expect(linkifyCitations("Claim [1, 3].")).toBe("Claim [1](#cite-1)[3](#cite-3).");
    expect(linkifyCitations("Claim [2-4].")).toBe("Claim [2](#cite-2)[3](#cite-3)[4](#cite-4).");
  });

  it("leaves code spans and fences alone", () => {
    const md = "Use `arr[1]` here [1].\n\n```js\nconst x = list[2];\n```\n";
    expect(linkifyCitations(md)).toBe("Use `arr[1]` here [1](#cite-1).\n\n```js\nconst x = list[2];\n```\n");
  });

  it("ignores things that only look like citations", () => {
    expect(linkifyCitations("[100] and [a] and [] stay")).toBe("[100] and [a] and [] stay");
  });
});

describe("citedNumbers", () => {
  it("returns the distinct sorted set of cited sources", () => {
    expect(citedNumbers("x [3] y [1][3] z [1, 2]")).toEqual([1, 2, 3]);
  });
});
