import Link from "next/link";
import { Wordmark } from "@/components/ui/Logo";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 bg-bg px-6 text-center text-ink">
      <Wordmark />
      <h1 className="font-display text-[2.4rem] font-medium leading-tight">That page isn&apos;t in the index.</h1>
      <p className="max-w-[40ch] text-ink-2">The link may be old, or the page moved. Your workspace is still where you left it.</p>
      <Link href="/app" className="inline-flex h-11 items-center rounded-2xl bg-accent px-5 text-sm font-medium text-accent-ink hover:bg-accent-strong">
        Open the workspace
      </Link>
    </main>
  );
}
