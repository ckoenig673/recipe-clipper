from __future__ import annotations

from html import escape
from html.parser import HTMLParser


_DANGEROUS_ELEMENT_NAMES = {
    "embed",
    "iframe",
    "noscript",
    "object",
    "script",
    "style",
    "template",
}
_URL_ATTRIBUTE_NAMES = {"action", "formaction", "href", "poster", "src", "srcset", "xlink:href"}
_UNSAFE_URL_PREFIXES = ("data:", "javascript:", "vbscript:")
_BLOCK_BREAK_TAGS = {
    "article",
    "aside",
    "blockquote",
    "body",
    "br",
    "caption",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}
_VOID_ELEMENT_NAMES = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def _normalize_script_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _has_unsafe_url(value: str) -> bool:
    normalized = "".join(str(value or "").strip().lower().split())
    return normalized.startswith(_UNSAFE_URL_PREFIXES)


def _sanitize_url_attribute(name: str, value: str) -> str | None:
    if not value:
        return ""
    if name != "srcset":
        return None if _has_unsafe_url(value) else value

    safe_candidates: list[str] = []
    for candidate in value.split(","):
        parts = candidate.strip().split()
        if not parts:
            continue
        url = parts[0]
        if _has_unsafe_url(url):
            continue
        safe_candidates.append(" ".join(parts))
    return ", ".join(safe_candidates) if safe_candidates else None


def _strip_json_wrappers(payload: str) -> str:
    cleaned = str(payload or "").strip()
    changed = True
    while changed and cleaned:
        changed = False
        if cleaned.startswith("<!--") and cleaned.endswith("-->"):
            cleaned = cleaned[4:-3].strip()
            changed = True
            continue
        if cleaned.startswith("<![CDATA[") and cleaned.endswith("]]>"):
            cleaned = cleaned[9:-3].strip()
            changed = True
            continue
        if cleaned.startswith("<!--"):
            cleaned = cleaned[4:].lstrip()
            changed = True
        if cleaned.endswith("-->"):
            cleaned = cleaned[:-3].rstrip()
            changed = True
        if cleaned.startswith("<![CDATA["):
            cleaned = cleaned[9:].lstrip()
            changed = True
        if cleaned.endswith("]]>"):
            cleaned = cleaned[:-3].rstrip()
            changed = True
    return cleaned


class _HtmlSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._pieces: list[str] = []
        self._blocked_stack: list[str] = []

    def get_html(self) -> str:
        return "".join(self._pieces)

    def handle_starttag(self, tag: str, attrs):
        name = tag.lower()
        if self._blocked_stack:
            if name in _DANGEROUS_ELEMENT_NAMES:
                self._blocked_stack.append(name)
            return
        if name in _DANGEROUS_ELEMENT_NAMES:
            self._blocked_stack.append(name)
            return
        self._pieces.append(f"<{name}")
        for attr_name, attr_value in attrs:
            normalized_name = (attr_name or "").lower()
            if not normalized_name or normalized_name.startswith("on"):
                continue
            if attr_value is None:
                self._pieces.append(f" {normalized_name}")
                continue
            normalized_value = attr_value
            if normalized_name in _URL_ATTRIBUTE_NAMES:
                normalized_value = _sanitize_url_attribute(normalized_name, attr_value)
                if normalized_value is None:
                    continue
            self._pieces.append(f' {normalized_name}="{escape(normalized_value, quote=True)}"')
        self._pieces.append(">")

    def handle_startendtag(self, tag: str, attrs):
        self.handle_starttag(tag, attrs)
        if not self._blocked_stack and tag.lower() not in _VOID_ELEMENT_NAMES:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str):
        name = tag.lower()
        if self._blocked_stack:
            if self._blocked_stack[-1] == name:
                self._blocked_stack.pop()
            return
        if name not in _VOID_ELEMENT_NAMES:
            self._pieces.append(f"</{name}>")

    def handle_data(self, data: str):
        if not self._blocked_stack and data:
            self._pieces.append(escape(data))

    def handle_entityref(self, name: str):
        if not self._blocked_stack:
            self._pieces.append(f"&{name};")

    def handle_charref(self, name: str):
        if not self._blocked_stack:
            self._pieces.append(f"&#{name};")


class _VisibleTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._blocked_stack: list[str] = []

    def get_text(self) -> str:
        return "".join(self._parts)

    def _append_break(self):
        if self._parts and self._parts[-1] != "\n":
            self._parts.append("\n")

    def handle_starttag(self, tag: str, attrs):
        name = tag.lower()
        if self._blocked_stack:
            if name in _DANGEROUS_ELEMENT_NAMES:
                self._blocked_stack.append(name)
            return
        if name in _DANGEROUS_ELEMENT_NAMES:
            self._blocked_stack.append(name)
            return
        if name in _BLOCK_BREAK_TAGS:
            self._append_break()

    def handle_endtag(self, tag: str):
        name = tag.lower()
        if self._blocked_stack:
            if self._blocked_stack[-1] == name:
                self._blocked_stack.pop()
            return
        if name in _BLOCK_BREAK_TAGS:
            self._append_break()

    def handle_data(self, data: str):
        if not self._blocked_stack and data:
            self._parts.append(data)


class _ScriptElementExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._scripts: list[tuple[dict[str, str], str]] = []
        self._buffer: list[str] | None = None
        self._attrs: dict[str, str] | None = None
        self._depth = 0

    def get_scripts(self) -> list[tuple[dict[str, str], str]]:
        return self._scripts

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "script":
            return
        if self._buffer is None:
            self._buffer = []
            self._attrs = {(name or "").lower(): value or "" for name, value in attrs if name}
            self._depth = 1
            return
        self._depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() != "script" or self._buffer is None:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        self._scripts.append((self._attrs or {}, "".join(self._buffer)))
        self._buffer = None
        self._attrs = None

    def handle_data(self, data: str):
        if self._buffer is not None and data:
            self._buffer.append(data)


def sanitize_html_document(html: str) -> str:
    parser = _HtmlSanitizer()
    parser.feed(html or "")
    parser.close()
    return parser.get_html()


def extract_visible_text(html: str) -> str:
    parser = _VisibleTextExtractor()
    parser.feed(html or "")
    parser.close()
    return parser.get_text()


def iter_script_elements(html: str, script_type: str | None = None) -> list[tuple[dict[str, str], str]]:
    parser = _ScriptElementExtractor()
    parser.feed(html or "")
    parser.close()
    if not script_type:
        return parser.get_scripts()
    expected = script_type.strip().lower()
    return [
        (attrs, content)
        for attrs, content in parser.get_scripts()
        if _normalize_script_type(attrs.get("type", "")) == expected
    ]


def extract_json_ld_payloads(html: str) -> list[str]:
    return [_strip_json_wrappers(content) for _, content in iter_script_elements(html, "application/ld+json")]
