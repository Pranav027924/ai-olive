import { Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

export interface DropdownOption<T extends string> {
  value: T;
  label: string;
  hint?: string;
}

interface DropdownProps<T extends string> {
  value: T;
  options: DropdownOption<T>[];
  onChange: (value: T) => void;
  "aria-label"?: string;
  align?: "left" | "right";
  /** Which way the menu opens. "top" suits a composer sitting at the bottom. */
  placement?: "top" | "bottom";
  className?: string;
}

/** A small custom select: a pill trigger + popover menu (no native <select>). */
export function Dropdown<T extends string>({
  value,
  options,
  onChange,
  align = "left",
  placement = "bottom",
  className,
  ...rest
}: DropdownProps<T>): JSX.Element {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div ref={ref} className={cn("relative", className)}>
      <button
        type="button"
        aria-label={rest["aria-label"]}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border border-border bg-background",
          "px-3.5 py-1.5 text-sm font-medium hover:bg-accent focus:outline-none",
        )}
      >
        {current?.label ?? value}
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <ul
            role="listbox"
            className={cn(
              "absolute z-20 min-w-[200px] overflow-hidden rounded-xl border border-border bg-card p-1 shadow-lg",
              placement === "top" ? "bottom-full mb-2" : "top-full mt-2",
              align === "right" ? "right-0" : "left-0",
            )}
          >
            {options.map((o) => (
              <li key={o.value}>
                <button
                  type="button"
                  role="option"
                  aria-selected={o.value === value}
                  onClick={() => {
                    onChange(o.value);
                    setOpen(false);
                  }}
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-accent"
                >
                  <span className="flex flex-col">
                    <span className="font-medium">{o.label}</span>
                    {o.hint && <span className="text-xs text-muted-foreground">{o.hint}</span>}
                  </span>
                  {o.value === value && <Check className="h-4 w-4 shrink-0" />}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
