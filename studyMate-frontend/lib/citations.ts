/**
 * Claude cites sources inline as `[1]`, `[2][3]` or `[1, 3]`. Before the
 * Markdown is rendered those markers are rewritten into links with a `#cite-n`
 * href, which the renderer turns into interactive chips. Code spans and fenced
 * blocks are left untouched.
 */

const CITE_GROUP = /\[(\d{1,2}(?:\s*[,–-]\s*\d{1,2})*)\]/g;

export function linkifyCitations(markdown: string): string {
  return mapOutsideCode(markdown, (text) =>
    text.replace(CITE_GROUP, (_match, inner: string) => {
      const numbers = expandRange(inner);
      if (numbers.length === 0) return _match;
      return numbers.map((n) => `[${n}](#cite-${n})`).join("");
    }),
  );
}

export function citedNumbers(markdown: string): number[] {
  const seen = new Set<number>();
  mapOutsideCode(markdown, (text) => {
    for (const match of text.matchAll(CITE_GROUP)) expandRange(match[1]).forEach((n) => seen.add(n));
    return text;
  });
  return [...seen].sort((a, b) => a - b);
}

function expandRange(inner: string): number[] {
  const out: number[] = [];
  for (const part of inner.split(",")) {
    const range = part.split(/[–-]/).map((p) => parseInt(p.trim(), 10));
    if (range.length === 2 && range.every(Number.isFinite) && range[1] >= range[0] && range[1] - range[0] <= 10) {
      for (let n = range[0]; n <= range[1]; n++) out.push(n);
    } else if (range.length === 1 && Number.isFinite(range[0])) {
      out.push(range[0]);
    }
  }
  return out.filter((n) => n >= 1 && n <= 50);
}

/** Apply `fn` to every stretch of text that is not inside a code fence or inline code span. */
function mapOutsideCode(markdown: string, fn: (text: string) => string): string {
  const parts = markdown.split(/(```[\s\S]*?```|`[^`\n]*`)/g);
  return parts.map((part, i) => (i % 2 === 1 ? part : fn(part))).join("");
}
