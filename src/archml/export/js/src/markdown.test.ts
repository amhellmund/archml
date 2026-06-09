// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// Unit tests for the viewer's Markdown renderer, focused on image support.

import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./viewer";

describe("renderMarkdown images", () => {
  it("renders a relative image as an <img> tag", () => {
    const html = renderMarkdown("![flow](out_assets/abc_flow.png)");
    expect(html).toContain('<img class="archml-md-img"');
    expect(html).toContain('src="out_assets/abc_flow.png"');
    expect(html).toContain('alt="flow"');
  });

  it("allows http(s) image URLs", () => {
    const html = renderMarkdown("![x](https://example.com/a.png)");
    expect(html).toContain('src="https://example.com/a.png"');
  });

  it("allows data:image URLs", () => {
    const html = renderMarkdown("![x](data:image/png;base64,AAAA)");
    expect(html).toContain('src="data:image/png;base64,AAAA"');
  });

  it("drops images with a disallowed scheme", () => {
    const html = renderMarkdown("![x](javascript:alert(1))");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("javascript:");
  });

  it("does not treat an image as a link", () => {
    const html = renderMarkdown("![x](pic.png)");
    expect(html).not.toContain("<a ");
  });
});

describe("renderMarkdown existing features", () => {
  it("still renders links, code, and headings", () => {
    expect(renderMarkdown("[t](https://e.com)")).toContain('<a href="https://e.com"');
    expect(renderMarkdown("`code`")).toContain("<code>code</code>");
    expect(renderMarkdown("# Title")).toContain('<h1 class="archml-md-h1">Title</h1>');
  });
});
