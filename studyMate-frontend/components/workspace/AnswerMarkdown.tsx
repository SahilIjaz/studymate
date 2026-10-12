"use client";

import { memo, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "@/lib/api";
import { linkifyCitations } from "@/lib/citations";
import { CitationChip } from "./CitationChip";

type Props = {
  content: string;
  citations: Citation[];
  activeCitation?: number | null;
  onSelectCitation?: (n: number) => void;
  streaming?: boolean;
};

export const AnswerMarkdown = memo(function AnswerMarkdown({
  content,
  citations,
  activeCitation,
  onSelectCitation,
  streaming,
}: Props) {
  const source = useMemo(() => linkifyCitations(content), [content]);
  const byNumber = useMemo(() => new Map(citations.map((c) => [c.n, c])), [citations]);

  const components = useMemo<Components>(
    () => ({
      a: ({ href, children, ...rest }) => {
        const match = href?.match(/^#cite-(\d+)$/);
        if (match) {
          const n = parseInt(match[1], 10);
          return <CitationChip n={n} citation={byNumber.get(n)} active={activeCitation === n} onSelect={onSelectCitation} />;
        }
        return (
          <a href={href} target="_blank" rel="noreferrer" {...rest}>
            {children}
          </a>
        );
      },
    }),
    [byNumber, activeCitation, onSelectCitation],
  );

  return (
    <div className={streaming ? "prose-answer caret" : "prose-answer"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {source}
      </ReactMarkdown>
    </div>
  );
});
