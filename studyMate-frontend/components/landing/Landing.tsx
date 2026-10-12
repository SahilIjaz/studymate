"use client";

import { ArrowRight, BookMarked, Layers, LockKeyhole, MessagesSquare, Quote, Zap } from "lucide-react";
import Link from "next/link";
import { motion } from "motion/react";
import { Wordmark } from "../ui/Logo";
import { ThemeToggle } from "../ui/ThemeToggle";
import { Architecture } from "./Architecture";
import { LiveDemo } from "./LiveDemo";

const ease = [0.16, 1, 0.3, 1] as const;

// Hero elements animate from transparent; everything below the fold starts
// visible (only translated) so the page is complete at rest.
const reveal = {
  hidden: { opacity: 0, y: 18 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: 0.08 * i, duration: 0.7, ease } }),
};
const rise = {
  hidden: { opacity: 0.5, y: 16 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: 0.07 * i, duration: 0.6, ease } }),
};

const features = [
  {
    icon: Quote,
    title: "Every claim has a page",
    body: "Answers cite the passage they came from, down to the page. Click a mark to read the original wording beside the answer.",
  },
  {
    icon: Layers,
    title: "Two searches, fused",
    body: "A semantic index catches paraphrases; a keyword index catches exact terms and symbols. Rank fusion merges them, so neither one has to be right alone.",
  },
  {
    icon: MessagesSquare,
    title: "Follow-ups that follow",
    body: "“Explain that more simply” works. The question is rewritten with the conversation in mind before the search runs.",
  },
  {
    icon: BookMarked,
    title: "Says when it doesn’t know",
    body: "Weak matches are cut before they reach the model. An off-topic question gets an honest “not in your documents”, not a confident guess.",
  },
  {
    icon: Zap,
    title: "Streams as it thinks",
    body: "Sources arrive first, then the answer, token by token. Stop it any time. Nothing blocks the server while a PDF is indexed.",
  },
  {
    icon: LockKeyhole,
    title: "Your workspace, your files",
    body: "Documents and conversations are isolated per workspace and persist across restarts. Uploads are sniffed, capped and rate-limited.",
  },
];

const steps = [
  { title: "Upload", body: "Drop in lecture notes, a chapter, a paper. Text is pulled page by page, repaired, and split into overlapping passages." },
  { title: "Ask", body: "Type the question the way you’d ask a tutor. Scope it to one document or search everything you’ve uploaded." },
  { title: "Read the proof", body: "The answer streams in with numbered marks. Each one opens the exact passage, so you can check it and keep reading." },
];

export function Landing() {
  return (
    <div className="min-h-dvh bg-bg text-ink">
      <header className="sticky top-0 z-40 border-b border-transparent bg-bg/75 backdrop-blur-md transition-colors [&.scrolled]:border-border">
        <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
          <Link href="/" className="rounded-lg">
            <Wordmark />
          </Link>
          <div className="flex items-center gap-1.5 sm:gap-3">
            <a href="#how" className="hidden rounded-lg px-3 py-2 text-sm text-ink-2 hover:text-ink sm:inline-flex">
              How it works
            </a>
            <a href="#architecture" className="hidden rounded-lg px-3 py-2 text-sm text-ink-2 hover:text-ink sm:inline-flex">
              Under the hood
            </a>
            <ThemeToggle />
            <Link
              href="/app"
              className="ml-1 inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent px-3 text-[13px] font-medium text-accent-ink shadow-[inset_0_-1px_0_rgba(0,0,0,0.12)] transition hover:bg-accent-strong active:translate-y-px"
            >
              Open workspace <ArrowRight size={14} />
            </Link>
          </div>
        </nav>
      </header>

      <main>
        {/* Hero */}
        <section className="grain relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 -z-0 opacity-70 [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_75%)]">
            <div className="ruled h-full w-full" />
          </div>
          <div className="relative mx-auto grid max-w-6xl gap-12 px-5 pb-20 pt-16 sm:px-8 sm:pt-24 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-10">
            <div>
              <motion.p variants={reveal} initial="hidden" animate="show" custom={0} className="eyebrow mb-5">
                Retrieval-augmented study assistant
              </motion.p>
              <motion.h1
                variants={reveal}
                initial="hidden"
                animate="show"
                custom={1}
                className="font-display text-[2.6rem] font-medium leading-[1.02] tracking-[-0.02em] sm:text-[3.6rem] lg:text-[4.1rem]"
              >
                Ask your notes.
                <br />
                Get the answer <span className="mark">and the page</span>.
              </motion.h1>
              <motion.p variants={reveal} initial="hidden" animate="show" custom={2} className="mt-6 max-w-[46ch] text-[17px] leading-relaxed text-ink-2">
                StudyMate reads the PDFs you upload and answers only from them, streamed from Gemini with a citation to the exact
                passage behind every claim.
              </motion.p>
              <motion.div variants={reveal} initial="hidden" animate="show" custom={3} className="mt-8 flex flex-wrap items-center gap-3">
                <Link
                  href="/app"
                  className="inline-flex h-12 items-center gap-2.5 rounded-2xl bg-accent px-6 text-[15px] font-medium text-accent-ink shadow-[inset_0_-1px_0_rgba(0,0,0,0.12)] transition hover:bg-accent-strong active:translate-y-px"
                >
                  Try it with your own PDF <ArrowRight size={16} />
                </Link>
                <a href="#how" className="inline-flex h-12 items-center rounded-2xl px-4 text-[15px] text-ink-2 hover:text-ink">
                  See how it works
                </a>
              </motion.div>
              <motion.ul variants={reveal} initial="hidden" animate="show" custom={4} className="mt-10 flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-ink-3">
                <li>No account needed</li>
                <li>PDFs up to 20 MB</li>
                <li>Free to try</li>
              </motion.ul>
            </div>
            <motion.div initial={{ opacity: 0, y: 24, rotate: -0.5 }} animate={{ opacity: 1, y: 0, rotate: 0 }} transition={{ delay: 0.35, duration: 0.9, ease }}>
              <LiveDemo />
            </motion.div>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="border-t bg-bg-2/60">
          <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-24">
            <div className="max-w-2xl">
              <p className="eyebrow mb-3">How it works</p>
              <h2 className="font-display text-[2rem] font-medium leading-[1.1] tracking-tight sm:text-[2.6rem]">
                Three steps, and the third one is the point.
              </h2>
            </div>
            <ol className="mt-12 grid gap-6 md:grid-cols-3">
              {steps.map((s, i) => (
                <motion.li
                  key={s.title}
                  variants={rise}
                  initial="hidden"
                  whileInView="show"
                  viewport={{ once: true, margin: "-10% 0px" }}
                  custom={i}
                  className="paper relative rounded-[22px] p-6"
                >
                  <span className="font-mono text-[12px] text-ink-3">{String(i + 1).padStart(2, "0")}</span>
                  <h3 className="mt-3 font-display text-[1.35rem] font-medium">{s.title}</h3>
                  <p className="mt-2 text-[14.5px] leading-relaxed text-ink-2">{s.body}</p>
                </motion.li>
              ))}
            </ol>
          </div>
        </section>

        {/* Features */}
        <section className="border-t">
          <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-24">
            <div className="max-w-2xl">
              <p className="eyebrow mb-3">What makes the answers trustworthy</p>
              <h2 className="font-display text-[2rem] font-medium leading-[1.1] tracking-tight sm:text-[2.6rem]">
                Built like a search engine, not a chatbot with a PDF attached.
              </h2>
            </div>
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {features.map((f, i) => (
                <motion.article
                  key={f.title}
                  variants={rise}
                  initial="hidden"
                  whileInView="show"
                  viewport={{ once: true, margin: "-10% 0px" }}
                  custom={i}
                  whileHover={{ y: -3 }}
                  className="paper group rounded-[22px] p-6 transition-colors hover:border-border-strong"
                >
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface-3 text-ink-2 ring-1 ring-border transition-colors group-hover:bg-accent-soft group-hover:text-ink">
                    <f.icon size={18} />
                  </span>
                  <h3 className="mt-4 text-[1.05rem] font-semibold">{f.title}</h3>
                  <p className="mt-1.5 text-[14px] leading-relaxed text-ink-2">{f.body}</p>
                </motion.article>
              ))}
            </div>
          </div>
        </section>

        {/* Architecture */}
        <section id="architecture" className="border-t bg-bg-2/60">
          <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-24">
            <div className="max-w-2xl">
              <p className="eyebrow mb-3">Under the hood</p>
              <h2 className="font-display text-[2rem] font-medium leading-[1.1] tracking-tight sm:text-[2.6rem]">What happens between the question and the answer.</h2>
              <p className="mt-4 text-[15.5px] leading-relaxed text-ink-2">
                FastAPI on the back, Next.js on the front. Each question runs a dense and a keyword search in parallel, fuses the
                rankings, drops weak matches, and hands the survivors to the model as numbered sources. The answer streams back over
                Server-Sent Events with the citations attached.
              </p>
            </div>
            <div className="mt-10">
              <Architecture />
            </div>
            <dl className="mt-8 grid gap-x-8 gap-y-4 text-[14px] sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["Embeddings", "bge-small via ONNX, no GPU, swappable for Voyage"],
                ["Index", "FAISS per workspace + BM25+, persisted to disk"],
                ["Model", "Gemini 3.8 Flash by default, Claude optional, overload fallback"],
                ["Tests", "44 backend tests, typed SSE contract, CI + Docker"],
              ].map(([k, v]) => (
                <div key={k} className="border-t pt-3">
                  <dt className="font-mono text-[11.5px] uppercase tracking-wider text-ink-3">{k}</dt>
                  <dd className="mt-1 text-ink-2">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* CTA */}
        <section className="border-t">
          <div className="mx-auto max-w-6xl px-5 py-20 text-center sm:px-8 sm:py-28">
            <h2 className="font-display text-[2.2rem] font-medium leading-[1.05] tracking-tight sm:text-[3rem]">
              Bring a chapter. <span className="mark">Leave with answers</span> you can check.
            </h2>
            <div className="mt-8 flex justify-center">
              <Link
                href="/app"
                className="inline-flex h-12 items-center gap-2.5 rounded-2xl bg-ink px-6 text-[15px] font-medium text-bg transition hover:opacity-90 active:translate-y-px"
              >
                Open the workspace <ArrowRight size={16} />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-8 text-[13px] text-ink-3 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <Wordmark className="text-ink" />
          <p>
            Built by{" "}
            <a href="https://github.com/SahilIjaz" className="text-ink underline-offset-4 hover:underline" target="_blank" rel="noreferrer">
              Sahil Ijaz
            </a>
            . FastAPI · Next.js · Gemini · FAISS.
          </p>
        </div>
      </footer>
    </div>
  );
}
