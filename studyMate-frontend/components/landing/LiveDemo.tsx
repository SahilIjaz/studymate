"use client";

import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { LogoMark } from "../ui/Logo";

/**
 * A scripted replay of a real StudyMate exchange. Nothing here calls the API;
 * it exists so the first screen shows what the product does instead of a
 * screenshot.
 */

const QUESTION = "What's the difference between the light reactions and the Calvin cycle?";

const SOURCES = [
  { n: 1, file: "biology-ch8.pdf", pages: "p. 164", score: 100 },
  { n: 2, file: "biology-ch8.pdf", pages: "p. 171", score: 82 },
  { n: 3, file: "lecture-12-notes.pdf", pages: "pp. 3–4", score: 64 },
];

type Token = { text: string; cite?: number };

const ANSWER: Token[] = [
  { text: "The " },
  { text: "light reactions", cite: undefined },
  { text: " happen in the thylakoid membranes and convert light into ATP and NADPH, releasing oxygen as a by-product" },
  { cite: 1, text: "" },
  { text: ". The " },
  { text: "Calvin cycle" },
  { text: " runs in the stroma and uses that ATP and NADPH to fix CO₂ into sugar" },
  { cite: 2, text: "" },
  { text: ".\n\nSo one captures energy, the other spends it. Your lecture notes put it as “light reactions make the fuel, the Calvin cycle builds with it”" },
  { cite: 3, text: "" },
  { text: "." },
];

const BOLD = new Set(["light reactions", "Calvin cycle"]);

type Phase = "idle" | "typing" | "retrieving" | "sources" | "writing" | "done";

export function LiveDemo() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10% 0px" });
  const reduce = useReducedMotion();
  const [phase, setPhase] = useState<Phase>("idle");
  const [typed, setTyped] = useState("");
  const [written, setWritten] = useState(0); // characters of the answer revealed
  const [cycle, setCycle] = useState(0);

  const total = ANSWER.reduce((n, t) => n + (t.cite ? 1 : t.text.length), 0);

  useEffect(() => {
    if (!inView) return;
    let cancelled = false;
    const timers: number[] = [];
    if (reduce) {
      // Skip the replay and show the finished exchange.
      timers.push(
        window.setTimeout(() => {
          setTyped(QUESTION);
          setWritten(total);
          setPhase("done");
        }, 0),
      );
      return () => timers.forEach(clearTimeout);
    }
    const wait = (ms: number) => new Promise<void>((r) => timers.push(window.setTimeout(r, ms)));

    (async () => {
      setPhase("idle");
      setTyped("");
      setWritten(0);
      await wait(600);
      setPhase("typing");
      for (let i = 1; i <= QUESTION.length && !cancelled; i++) {
        setTyped(QUESTION.slice(0, i));
        await wait(QUESTION[i - 1] === " " ? 55 : 28);
      }
      await wait(350);
      setPhase("retrieving");
      await wait(900);
      setPhase("sources");
      await wait(1100);
      setPhase("writing");
      for (let i = 1; i <= total && !cancelled; i++) {
        setWritten(i);
        await wait(14);
      }
      setPhase("done");
      await wait(6000);
      if (!cancelled) setCycle((c) => c + 1);
    })();

    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, [inView, reduce, total, cycle]);

  // Render the answer up to `written` characters, keeping citations atomic.
  let budget = written;
  const parts: React.ReactNode[] = [];
  ANSWER.forEach((token, i) => {
    if (budget <= 0) return;
    if (token.cite) {
      budget -= 1;
      parts.push(
        <motion.span
          key={i}
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 500, damping: 24 }}
          className="mx-0.5 inline-flex h-[1.2em] min-w-[1.5em] -translate-y-[0.1em] items-center justify-center rounded-[5px] bg-mark px-1 align-middle font-mono text-[0.68em] font-medium text-mark-ink ring-1 ring-inset ring-accent/40"
        >
          {token.cite}
        </motion.span>,
      );
      return;
    }
    const slice = token.text.slice(0, budget);
    budget -= token.text.length;
    const node = BOLD.has(token.text) ? <strong key={i}>{slice}</strong> : <span key={i}>{slice}</span>;
    parts.push(node);
  });

  return (
    <div ref={ref} className="paper relative mx-auto w-full max-w-[640px] overflow-hidden rounded-[22px] text-left">
      <div className="flex h-10 items-center gap-2 border-b bg-surface-2 px-4">
        <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
        <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
        <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
        <span className="ml-2 font-mono text-[11px] text-ink-3">studymate · biology-ch8.pdf, lecture-12-notes.pdf</span>
      </div>

      <div className="flex min-h-[380px] flex-col gap-5 p-5 sm:p-6">
        {/* question */}
        <div className="flex justify-end">
          <div className="max-w-[88%] rounded-[18px] rounded-br-md bg-user px-4 py-2.5 text-[14px] leading-relaxed text-user-fg">
            {typed}
            {phase === "typing" && <span className="caret" />}
            {phase === "idle" && <span className="text-user-fg/50">Ask a question…</span>}
          </div>
        </div>

        {/* status / sources */}
        <AnimatePresence initial={false}>
          {phase === "retrieving" && (
            <motion.div
              key="status"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="flex items-center gap-2 text-[13px] text-ink-3"
            >
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-accent-strong" />
              </span>
              Searching 2 documents…
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence initial={false}>
          {(phase === "sources" || phase === "writing" || phase === "done") && (
            <motion.div key="sources" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-wrap gap-1.5">
              {SOURCES.map((s, i) => (
                <motion.span
                  key={s.n}
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.12, type: "spring", stiffness: 400, damping: 28 }}
                  className="inline-flex items-center gap-1.5 rounded-lg border bg-surface-2 py-1 pl-1.5 pr-2.5 text-[12px] text-ink-2"
                >
                  <span className="flex h-5 min-w-5 items-center justify-center rounded-[4px] bg-mark px-1 font-mono text-[11px] text-mark-ink">
                    {s.n}
                  </span>
                  <span className="max-w-[140px] truncate">{s.file}</span>
                  <span className="tabular text-ink-3">{s.pages}</span>
                </motion.span>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* answer */}
        <AnimatePresence initial={false}>
          {(phase === "writing" || phase === "done") && (
            <motion.div key="answer" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
              <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-surface-2 ring-1 ring-border">
                <LogoMark size={18} />
              </div>
              <p className={`min-w-0 flex-1 whitespace-pre-wrap text-[14px] leading-relaxed ${phase === "writing" ? "caret" : ""}`}>{parts}</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
