import { cn } from "@/lib/utils";

/** A page with a highlighter stroke across it. */
export function LogoMark({ className, size = 28 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className={cn("shrink-0", className)}
    >
      <rect x="6" y="3" width="20" height="26" rx="3.5" className="fill-surface stroke-ink" strokeWidth="2" />
      <path d="M11 10h10M11 15h10M11 20h6" className="stroke-ink-3" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M8.5 23.5 23 11.5" className="stroke-accent" strokeWidth="5" strokeLinecap="round" opacity="0.9" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="font-display text-[1.15rem] font-semibold tracking-tight">StudyMate</span>
    </span>
  );
}
