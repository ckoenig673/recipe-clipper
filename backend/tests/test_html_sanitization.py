from backend.app.html_sanitization import extract_visible_text, iter_script_elements, sanitize_html_document
from backend.app.main import extract_json_ld_blocks


def test_sanitize_html_document_removes_active_content_and_unsafe_attributes():
    html = """
    <article class="recipe-card" onclick="alert(1)">
      <p>Safe intro <a href="javascript:alert(1)" onmouseover="alert(2)">bad link</a>.</p>
      <img src="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==" onerror="alert(3)" alt="hero">
      <iframe src="https://evil.example/embed"></iframe>
      <script>alert("boom")</script>
      <div data-role="content">1 cup broth</div>
    </article>
    """

    sanitized = sanitize_html_document(html)

    assert "<script" not in sanitized
    assert "<iframe" not in sanitized
    assert "onclick=" not in sanitized
    assert "onmouseover=" not in sanitized
    assert "onerror=" not in sanitized
    assert 'href="javascript:alert(1)"' not in sanitized
    assert "data:text/html" not in sanitized
    assert 'class="recipe-card"' in sanitized
    assert "1 cup broth" in sanitized


def test_extract_visible_text_ignores_script_style_and_noscript_content():
    html = """
    <html>
      <head>
        <style>.recipe{display:none}</style>
        <script>window.leak = "do not include";</script>
      </head>
      <body>
        <article>
          <h1>Tomato Soup</h1>
          <noscript>fallback tracking text</noscript>
          <p>Simmer tomatoes gently.</p>
        </article>
      </body>
    </html>
    """

    text = extract_visible_text(html)

    assert "Tomato Soup" in text
    assert "Simmer tomatoes gently." in text
    assert "do not include" not in text
    assert "fallback tracking text" not in text


def test_extract_json_ld_blocks_handles_wrapped_payloads_and_keeps_recipe_markup():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          <!--{"@type":"Recipe","name":"Soup","description":"<b>Bold</b> broth"}-->
        </script>
        <script type="application/ld+json">
          <![CDATA[[{"@type":"Recipe","name":"Cake"}]]]>
        </script>
        <script type="application/ld+json">not-json</script>
      </head>
    </html>
    """

    blocks = extract_json_ld_blocks(html)

    assert [block.get("name") for block in blocks] == ["Soup", "Cake"]
    assert blocks[0]["description"] == "<b>Bold</b> broth"


def test_iter_script_elements_handles_nested_markup_without_regex_html_scans():
    html = """
    <html>
      <body>
        <script type="application/ld+json">
          {"url":"https://example.com/recipe"}
        </script>
        <script>
          window.recipeUrl = "https://example.com/from-inline";
        </script>
      </body>
    </html>
    """

    jsonld_scripts = iter_script_elements(html, "application/ld+json")
    all_scripts = iter_script_elements(html)

    assert len(jsonld_scripts) == 1
    assert "https://example.com/recipe" in jsonld_scripts[0][1]
    assert len(all_scripts) == 2
    assert "https://example.com/from-inline" in all_scripts[1][1]
