"use client";

import { motion, useInView } from "motion/react";
import { useRef } from "react";

/**
 * The retrieval pipeline, drawn to scale of what actually happens per
 * question. Dashed edges animate so the flow direction reads at a glance.
 */
const nodes = [
  { id: "q", x: 20, y: 110, w: 120, label: "Question", sub: "rewritten if a follow-up" },
  { id: "d", x: 190, y: 40, w: 150, label: "Dense search", sub: "FAISS · cosine" },
  { id: "s", x: 190, y: 180, w: 150, label: "Keyword search", sub: "BM25+" },
  { id: "f", x: 390, y: 110, w: 140, label: "Rank fusion", sub: "RRF · cutoff · top 6" },
  { id: "c", x: 580, y: 110, w: 150, label: "Gemini", sub: "streamed · fallback model" },
  { id: "a", x: 780, y: 110, w: 120, label: "Answer", sub: "with [n] citations" },
];

const edges = [
  ["q", "d"],
  ["q", "s"],
  ["d", "f"],
  ["s", "f"],
  ["f", "c"],
  ["c", "a"],
];

const H = 56;

function center(id: string) {
  const n = nodes.find((x) => x.id === id)!;
  return { x: n.x + n.w / 2, y: n.y + H / 2, left: n.x, right: n.x + n.w };
}

export function Architecture() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-15% 0px" });

  return (
    <div ref={ref} className="paper overflow-x-auto rounded-[22px] p-4 sm:p-6">
      <svg viewBox="0 0 920 280" className="mx-auto block min-w-[760px] max-w-[920px]" role="img" aria-label="Pipeline: question to dense and keyword search, fused, sent to Gemini, answered with citations">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0L10 5 0 10z" className="fill-ink-3" />
          </marker>
        </defs>
        {edges.map(([from, to], i) => {
          const a = center(from);
          const b = center(to);
          const midX = (a.right + b.left) / 2;
          const d = `M${a.right} ${a.y} C ${midX} ${a.y}, ${midX} ${b.y}, ${b.left - 2} ${b.y}`;
          return (
            <motion.path
              key={`${from}-${to}`}
              d={d}
              fill="none"
              className="flow-line stroke-ink-3"
              strokeWidth="1.5"
              markerEnd="url(#arrow)"
              initial={{ pathLength: 0, opacity: 0.4 }}
              animate={inView ? { pathLength: 1, opacity: 1 } : {}}
              transition={{ delay: 0.3 + i * 0.12, duration: 0.6, ease: "easeOut" }}
            />
          );
        })}
        {nodes.map((n, i) => (
          <motion.g
            key={n.id}
            initial={{ opacity: 0.5, y: 8 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: i * 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          >
            <rect x={n.x} y={n.y} width={n.w} height={H} rx="12" className={n.id === "c" ? "fill-accent" : "fill-surface-2 stroke-border-strong"} strokeWidth="1" />
            <text x={n.x + n.w / 2} y={n.y + 23} textAnchor="middle" className={`text-[13px] font-medium ${n.id === "c" ? "fill-accent-ink" : "fill-ink"}`} style={{ fontFamily: "var(--font-sans)" }}>
              {n.label}
            </text>
            <text x={n.x + n.w / 2} y={n.y + 41} textAnchor="middle" className={`text-[11px] ${n.id === "c" ? "fill-accent-ink/70" : "fill-ink-3"}`} style={{ fontFamily: "var(--font-mono)" }}>
              {n.sub}
            </text>
          </motion.g>
        ))}
        <text x="20" y="262" className="fill-ink-3 text-[11px]" style={{ fontFamily: "var(--font-mono)" }}>
          Per workspace: SQLite (chunks, conversations) · FAISS index file · uploaded PDFs. Indexing runs in the background per upload.
        </text>
      </svg>
    </div>
  );
}
