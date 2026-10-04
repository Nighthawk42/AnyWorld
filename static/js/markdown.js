"use strict";

(function () {
    // Configure marked with GitHub-flavored markdown and soft line breaks
    if (typeof marked !== "undefined" && marked.setOptions) {
        marked.setOptions({
            gfm: true,
            breaks: true,
            headerIds: false,
            mangle: false,
        });
    }

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function sanitize(dirtyHtml) {
        if (typeof DOMPurify !== "undefined" && DOMPurify.sanitize) {
            return DOMPurify.sanitize(dirtyHtml, {
                ALLOWED_TAGS: [
                    "p", "br", "strong", "b", "em", "i", "s", "del", "code", "pre",
                    "blockquote", "ul", "ol", "li", "hr", "a", "h1", "h2", "h3",
                    "h4", "h5", "h6", "table", "thead", "tbody", "tr", "th", "td",
                    "span"
                ],
                ALLOWED_ATTR: ["href", "title", "target", "rel", "class"],
            });
        }
        return dirtyHtml;
    }

    /**
     * Render full block-level markdown text with sanitization.
     * Suitable for scenario descriptions, round state narrative, etc.
     */
    function renderMarkdown(text) {
        if (!text || typeof text !== "string") return "";
        if (typeof marked === "undefined" || !marked.parse) {
            return `<p>${escapeHtml(text)}</p>`;
        }
        try {
            const rawHtml = marked.parse(text);
            return sanitize(rawHtml);
        } catch {
            return `<p>${escapeHtml(text)}</p>`;
        }
    }

    /**
     * Render inline markdown without wrapping <p> tags.
     * Suitable for chat messages, actions, and player resolutions.
     */
    function renderMarkdownInline(text) {
        if (!text || typeof text !== "string") return "";
        if (typeof marked === "undefined") {
            return escapeHtml(text);
        }
        try {
            const rawHtml = marked.parseInline ? marked.parseInline(text) : marked.parse(text);
            return sanitize(rawHtml);
        } catch {
            return escapeHtml(text);
        }
    }

    window.renderMarkdown = renderMarkdown;
    window.renderMarkdownInline = renderMarkdownInline;
})();
