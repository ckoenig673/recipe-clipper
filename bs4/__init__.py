from __future__ import annotations

from html.parser import HTMLParser
import re


class _Node:
    def __init__(self, name: str, attrs: dict[str, str] | None = None, parent: "_Node | None" = None):
        self.name = name.lower()
        self.attrs = attrs or {}
        self.parent = parent
        self.children: list[_Node] = []
        self.text_parts: list[str] = []

    def append_child(self, child: "_Node") -> None:
        self.children.append(child)

    def append_text(self, text: str) -> None:
        if text:
            self.text_parts.append(text)

    def _iter_descendants(self):
        for child in self.children:
            yield child
            yield from child._iter_descendants()

    def _class_tokens(self) -> set[str]:
        class_value = self.attrs.get("class", "")
        return {token for token in re.split(r"\s+", class_value.strip()) if token}

    def select_one(self, selector: str):
        if selector.startswith("."):
            class_name = selector[1:]
            for node in self._iter_descendants():
                if class_name in node._class_tokens():
                    return node
            return None
        return self.find(selector)

    def find(self, name: str):
        expected = name.lower()
        for node in self._iter_descendants():
            if node.name == expected:
                return node
        return None

    @property
    def body(self):
        return self.find("body")

    def get_text(self, separator: str = "") -> str:
        chunks: list[str] = []
        self._collect_text(chunks)
        return separator.join(chunk for chunk in chunks if chunk != "")

    def _collect_text(self, chunks: list[str]) -> None:
        for part in self.text_parts:
            if part:
                chunks.append(part)
        for child in self.children:
            child._collect_text(chunks)


class _SoupParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("[document]")
        self.stack: list[_Node] = [self.root]

    def handle_starttag(self, tag, attrs):
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        node = _Node(tag, attr_map, parent=self.stack[-1])
        self.stack[-1].append_child(node)
        self.stack.append(node)

    def handle_endtag(self, tag):
        for idx in range(len(self.stack) - 1, 0, -1):
            if self.stack[idx].name == tag.lower():
                self.stack = self.stack[:idx]
                return

    def handle_data(self, data):
        if self.stack:
            self.stack[-1].append_text(data)


class BeautifulSoup(_Node):
    def __init__(self, markup: str, _parser: str = "html.parser"):
        parser = _SoupParser()
        parser.feed(markup or "")
        parser.close()
        super().__init__("[document]")
        self.children = parser.root.children
        for child in self.children:
            child.parent = self
