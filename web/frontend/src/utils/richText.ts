import createDOMPurify from "dompurify";

// Match the comment formats accepted by the API and the station PDF.
const purifier = createDOMPurify(window);
const classes: Record<string, Set<string>> = {
    span: new Set(["ql-size-small", "ql-size-normal", "ql-size-large", "ql-size-huge"]),
    pre: new Set(["ql-syntax"]),
    ol: new Set(["list-decimal", "ps-[19.5px]", "pl-[19.5px]"]),
    ul: new Set(["list-disc", "ps-[19.5px]", "pl-[19.5px]"]),
};

purifier.addHook("uponSanitizeAttribute", (node, attr) => {
    if (attr.attrName === "class") {
        const allowed = classes[node.localName];
        attr.attrValue = attr.attrValue.split(/\s+/).filter((name) => allowed?.has(name)).join(" ");
        attr.keepAttr = Boolean(attr.attrValue);
    } else if (attr.attrName === "href") {
        attr.keepAttr = node.localName === "a";
    } else if (attr.attrName === "target") {
        attr.keepAttr = node.localName === "a" && attr.attrValue === "_blank";
    }
});

purifier.addHook("afterSanitizeAttributes", (node) => {
    if (node.localName === "a" && node.hasAttribute("href")) {
        node.setAttribute("rel", "noopener noreferrer");
    }
});

export function sanitizeRichText(value?: string | null): string {
    return purifier.sanitize(value ?? "", {
        ALLOWED_TAGS: ["p", "br", "strong", "b", "em", "i", "s", "strike", "u", "code",
            "pre", "ol", "ul", "li", "blockquote", "span", "a"],
        ALLOWED_ATTR: ["class", "href", "target"],
        ADD_URI_SAFE_ATTR: ["target"],
        ALLOW_DATA_ATTR: false,
        ALLOW_ARIA_ATTR: false,
        ALLOWED_URI_REGEXP: /^(?:https?:\/\/|mailto:)/i,
    });
}
