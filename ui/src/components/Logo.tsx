import { cn } from "@/lib/cn";

/** Hand-drawn-ish olive ring mark. */
export function Logo({ className }: { className?: string }): JSX.Element {
  return (
    <svg viewBox="0 0 100 100" className={cn("text-foreground", className)} aria-hidden>
      <path
        d="M50 8
           C72 8 90 26 90 50
           C90 74 72 92 50 92
           C28 92 10 74 10 50
           C10 28 26 12 46 11"
        fill="none"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}
