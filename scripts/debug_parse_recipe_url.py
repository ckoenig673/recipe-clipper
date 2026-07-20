#!/usr/bin/env python3
import json
import re
import sys
from html import unescape

import requests
from bs4 import BeautifulSoup


def clean(text):
    text = BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_jsonld(soup):
    recipes = []

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        def walk(node):
            if isinstance(node, dict):
                graph = node.get("@graph")
                if isinstance(graph, list):
                    for item in graph:
                        walk(item)

                types = node.get("@type")
                if isinstance(types, str):
                    types = [types]

                if types and any(str(t).lower() == "recipe" for t in types):
                    recipes.append(node)

                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)

            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)

    return recipes


def extract_jsonld_instructions(recipe):
    out = []

    def step_text(item):
        if isinstance(item, str):
            return clean(item)
        if isinstance(item, dict):
            return clean(item.get("text") or item.get("name") or "")
        return ""

    def walk_instruction(item, current_group="Instructions"):
        if isinstance(item, str):
            txt = clean(item)
            if txt:
                out.append((current_group, txt))
            return

        if isinstance(item, dict):
            item_type = item.get("@type")
            if isinstance(item_type, list):
                item_type = item_type[0] if item_type else ""

            if str(item_type).lower() == "howtosection":
                group = clean(item.get("name") or current_group)
                children = item.get("itemListElement") or item.get("steps") or []
                if isinstance(children, list):
                    for child in children:
                        walk_instruction(child, group)
                return

            txt = step_text(item)
            if txt:
                out.append((current_group, txt))
            return

        if isinstance(item, list):
            for child in item:
                walk_instruction(child, current_group)

    walk_instruction(recipe.get("recipeInstructions") or [])
    return out


def extract_wprm_dom(soup):
    container = soup.select_one(".wprm-recipe-instructions-container")
    if not container:
        return []

    groups = []

    def step_texts(scope):
        steps = []
        for el in scope.select(".wprm-recipe-instruction-text, .wprm-recipe-instruction"):
            txt = clean(str(el))
            if txt:
                steps.append(txt)
        return steps

    # Clone-ish strategy: get direct/main steps that are not inside a named group.
    main_steps = []
    for el in container.select(".wprm-recipe-instruction-text, .wprm-recipe-instruction"):
        if el.find_parent(class_="wprm-recipe-instruction-group"):
            continue
        txt = clean(str(el))
        if txt:
            main_steps.append(txt)

    if main_steps:
        groups.append(("Instructions", main_steps))

    for group in container.select(".wprm-recipe-instruction-group"):
        title_el = group.select_one(".wprm-recipe-group-name")
        title = clean(str(title_el)) if title_el else ""
        steps = step_texts(group)
        if steps:
            groups.append((title or "Instructions", steps))

    return groups


def extract_wprm_ingredients(soup):
    container = soup.select_one(".wprm-recipe-ingredients-container")
    if not container:
        return []

    groups = []

    def ingredient_texts(scope):
        items = []
        for el in scope.select(".wprm-recipe-ingredient"):
            txt = clean(str(el))
            if txt:
                items.append(txt)
        return items

    main_items = []
    for el in container.select(".wprm-recipe-ingredient"):
        if el.find_parent(class_="wprm-recipe-ingredient-group"):
            continue
        txt = clean(str(el))
        if txt:
            main_items.append(txt)

    if main_items:
        groups.append(("Ingredients", main_items))

    for group in container.select(".wprm-recipe-ingredient-group"):
        title_el = group.select_one(".wprm-recipe-group-name")
        title = clean(str(title_el)) if title_el else ""
        items = ingredient_texts(group)
        if items:
            groups.append((title or "Ingredients", items))

    return groups


def print_grouped(title, groups):
    print(f"\n=== {title} ===")
    if not groups:
        print("NONE")
        return

    for group_title, items in groups:
        print(f"\n## {group_title}")
        for i, item in enumerate(items, 1):
            print(f"{i}. {item}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_parse_recipe_url.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    headers = {
        "User-Agent": "Mozilla/5.0 RecipeParserDebug/1.0",
        "Accept": "text/html,application/xhtml+xml",
    }

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    print(f"URL: {url}")
    print(f"Status: {resp.status_code}")
    print(f"HTML length: {len(html)}")
    print(f"Title: {clean(str(soup.title)) if soup.title else ''}")

    recipes = extract_jsonld(soup)
    print(f"\nJSON-LD recipe count: {len(recipes)}")

    for idx, recipe in enumerate(recipes, 1):
        print(f"\n=== JSON-LD Recipe #{idx} ===")
        print("Name:", clean(recipe.get("name") or ""))
        ingredients = [clean(x) for x in recipe.get("recipeIngredient", []) if clean(x)]
        print_grouped("JSON-LD Ingredients", [("Ingredients", ingredients)])

        instructions = extract_jsonld_instructions(recipe)
        grouped = {}
        for group, step in instructions:
            grouped.setdefault(group, []).append(step)
        print_grouped("JSON-LD Instructions", list(grouped.items()))

    print_grouped("WPRM DOM Ingredients", extract_wprm_ingredients(soup))
    print_grouped("WPRM DOM Instructions", extract_wprm_dom(soup))

    # Dump selector counts for troubleshooting.
    selectors = [
        ".wprm-recipe-instructions-container",
        ".wprm-recipe-instruction-group",
        ".wprm-recipe-instruction-text",
        ".wprm-recipe-instruction",
        ".wprm-recipe-ingredients-container",
        ".wprm-recipe-ingredient-group",
        ".wprm-recipe-ingredient",
        ".wprm-recipe-group-name",
    ]

    print("\n=== Selector counts ===")
    for selector in selectors:
        print(f"{selector}: {len(soup.select(selector))}")


if __name__ == "__main__":
    main()
