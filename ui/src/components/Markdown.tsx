import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/cn";

/**
 * Renders an assistant message as GitHub-flavoured markdown with a
 * ChatGPT-like reading layout: real headings, bullet/numbered lists,
 * bold/italics, code blocks, tables, links, and comfortable spacing.
 */
export function Markdown({ content, className }: { content: string; className?: string }): JSX.Element {
  return (
    <div
      className={cn(
        "prose prose-neutral max-w-none dark:prose-invert",
        // tighten + theme a few things to match the chat surface
        "prose-headings:font-semibold prose-headings:tracking-tight",
        "prose-p:leading-7 prose-li:my-0.5 prose-pre:my-3",
        "prose-pre:rounded-xl prose-pre:border prose-pre:border-border prose-pre:bg-muted prose-pre:text-foreground",
        "prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:font-normal",
        "prose-code:before:content-none prose-code:after:content-none",
        "prose-a:text-foreground prose-a:underline prose-a:underline-offset-2",
        "prose-hr:border-border",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ ...props }) => <a {...props} target="_blank" rel="noreferrer noopener" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
