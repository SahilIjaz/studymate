import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnswerMarkdown } from "@/components/workspace/AnswerMarkdown";
import type { Citation } from "@/lib/api";

const citation: Citation = {
  n: 1,
  chunk_id: 7,
  document_id: "doc_1",
  filename: "biology.pdf",
  page_start: 3,
  page_end: 4,
  score: 0.9,
  text: "Photosynthesis happens in chloroplasts.",
};

describe("AnswerMarkdown", () => {
  it("renders citation markers as chips that report their source on click", () => {
    const onSelect = vi.fn();
    render(
      <AnswerMarkdown content={"**Chloroplasts** host photosynthesis [1]."} citations={[citation]} onSelectCitation={onSelect} />,
    );
    expect(screen.getByText("Chloroplasts").tagName).toBe("STRONG");
    const chip = screen.getByRole("button", { name: /Source 1: biology.pdf, pp. 3–4/ });
    fireEvent.click(chip);
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("opens ordinary links in a new tab", () => {
    render(<AnswerMarkdown content={"See [docs](https://example.com)."} citations={[]} />);
    const link = screen.getByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });
});
