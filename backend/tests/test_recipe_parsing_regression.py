import unittest
from unittest.mock import patch

from backend.app.main import _extract_wprm_instruction_groups, fetch_recipe_data_from_url


SUGARSPUNRUN_CHEESECAKE_FIXTURE_HTML = """
<html>
<head>
  <title>The Best Cheesecake Recipe - Sugar Spun Run</title>
  <script type=\"application/ld+json\">{
    \"@context\": \"https://schema.org\",
    \"@type\": \"Recipe\",
    \"name\": \"The BEST Cheesecake Recipe\",
    \"recipeIngredient\": [
      \"1 1/2 cups graham cracker crumbs\",
      \"2 tablespoons sugar\",
      \"32 oz cream cheese\",
      \"4 large eggs\"
    ],
    \"recipeInstructions\": [
      {\"@type\": \"HowToStep\", \"text\": \"Preheat oven to 325F.\"},
      {\"@type\": \"HowToStep\", \"text\": \"Beat cream cheese and sugar until smooth.\"},
      {\"@type\": \"HowToStep\", \"text\": \"Add eggs one at a time.\"}
    ]
  }</script>
</head>
<body>
  <nav>
    <ul>
      <li class=\"ingredients\">Sign up for free daily recipes!</li>
      <li class=\"ingredients\">Home</li>
      <li class=\"ingredients\">Recipe Index</li>
      <li class=\"ingredients\">4.96 from 3472 votes</li>
      <li class=\"ingredients\">This post may contain affiliate links.</li>
    </ul>
  </nav>

  <article class=\"entry-content\">
    <p>By Sam Merritt Published Jan 30, 2019</p>
    <p>Today I'm excited to show you how to make cheesecake.</p>
    <div class=\"comments\">7,590 comments</div>

    <div class=\"recipe-card\">
      <h3>Ingredients</h3>
      <ul class=\"ingredients\">
        <li>32 oz cream cheese</li>
        <li>1 cup sugar</li>
        <li>4 large eggs</li>
      </ul>

      <h3>Instructions</h3>
      <ol class=\"instructions\">
        <li>Mix ingredients.</li>
        <li>Bake until set.</li>
      </ol>
    </div>
  </article>
</body>
</html>
"""

OH_SNAP_BIG_MAC_BOWLS_FIXTURE_HTML = """
<html>
<head>
  <title>Big Mac Bowls</title>
  <script type="application/ld+json">{
    "@context": "https://schema.org",
    "@type": "Recipe",
    "name": "Big Mac Bowls",
    "recipeIngredient": [
      "1 lb ground beef",
      "1 tsp kosher salt",
      "2 cups chopped lettuce",
      "1 cup shredded cheese"
    ],
    "recipeInstructions": [
      {
        "@type": "HowToSection",
        "name": "Main",
        "itemListElement": [
          {"@type": "HowToStep", "text": "Cook beef and season."}
        ]
      },
      {
        "@type": "HowToSection",
        "name": "Bowl Assembly",
        "itemListElement": [
          {"@type": "HowToStep", "text": "Layer lettuce, beef, and toppings."}
        ]
      },
      {
        "@type": "HowToSection",
        "name": "Meal Prep Assembly",
        "itemListElement": [
          {"@type": "HowToStep", "text": "Pack ingredients into containers."}
        ]
      }
    ]
  }</script>
</head>
<body></body>
</html>
"""

OH_SNAP_BIG_MAC_BOWLS_WPRM_HTML = """
<html>
<body>
  <div class="wprm-recipe-instructions-container">
    <div class="wprm-recipe-instruction-text">Spray a large skillet and cook the beef with onion over medium heat until browned.</div>
    <div class="wprm-recipe-instruction-text">Add garlic powder, onion powder, salt, pepper, and mustard. Stir to combine.</div>
    <div class="wprm-recipe-instruction-text">Mix mayonnaise, ketchup, chopped pickles, and pickle juice in a small bowl.</div>
    <div class="wprm-recipe-instruction-text">Assemble bowls with lettuce, beef mixture, cheese, and sauce.</div>

    <div class="wprm-recipe-instruction-group">
      <h4 class="wprm-recipe-group-name">Bowl Assembly</h4>
      <div class="wprm-recipe-instruction-text">Layer lettuce, beef, cheese, and toppings in each bowl.</div>
    </div>
    <div class="wprm-recipe-instruction-group">
      <h4 class="wprm-recipe-group-name">Meal Prep Assembly</h4>
      <div class="wprm-recipe-instruction-text">Divide ingredients into containers and keep sauce separate.</div>
    </div>
  </div>
</body>
</html>
"""

FLAT_JSONLD_STRUCTURED_DOM_FIXTURE_HTML = """
<html>
<head>
  <title>Big Mac Bowls</title>
  <script type="application/ld+json">{
    "@context": "https://schema.org",
    "@type": "Recipe",
    "name": "Big Mac Bowls",
    "recipeYield": "4 bowls",
    "prepTime": "PT15M",
    "cookTime": "PT20M",
    "totalTime": "PT35M",
    "image": "https://example.com/big-mac-bowls.jpg",
    "recipeIngredient": [
      "1 lb ground beef",
      "1/2 cup mayo",
      "8 cups chopped lettuce"
    ],
    "recipeInstructions": [
      {"@type": "HowToStep", "text": "Cook beef and season."},
      {"@type": "HowToStep", "text": "Assemble bowls and serve."}
    ]
  }</script>
</head>
<body></body>
</html>
"""

BIG_MAC_BOWLS_FULL_JSONLD_FIXTURE_HTML = """
<html>
<head>
  <title>Big Mac Bowls</title>
  <script type="application/ld+json">{
    "@context":"https://schema.org",
    "@type":"Recipe",
    "name":"Big Mac Bowls",
    "recipeIngredient":[
      "1 lb lean ground beef","1 teaspoon kosher salt","1/2 teaspoon black pepper",
      "1 teaspoon garlic powder","1 teaspoon onion powder","1/2 cup mayonnaise",
      "2 tablespoons ketchup","1 tablespoon yellow mustard","2 tablespoons pickle relish",
      "6 cups chopped lettuce","1 cup shredded cheddar","1/2 cup diced white onion",
      "1 cup diced tomatoes","1/2 cup sliced pickles","4 meal-prep containers",
      "1 tablespoon olive oil","sesame seeds for garnish"
    ],
    "recipeInstructions":[
      {"@type":"HowToSection","name":"Main Instructions","itemListElement":[
        {"@type":"HowToStep","text":"Heat oil and brown beef in a skillet."},
        {"@type":"HowToStep","text":"Season beef with salt, pepper, garlic powder, and onion powder."},
        {"@type":"HowToStep","text":"Whisk mayo, ketchup, mustard, and relish to make sauce."}
      ]},
      {"@type":"HowToSection","name":"Bowl Assembly","itemListElement":[
        {"@type":"HowToStep","text":"Layer lettuce, beef, cheddar, onion, tomatoes, and pickles."},
        {"@type":"HowToStep","text":"Drizzle with sauce and top with sesame seeds."}
      ]},
      {"@type":"HowToSection","name":"Meal Prep Assembly","itemListElement":[
        {"@type":"HowToStep","text":"Divide ingredients among containers and store sauce separately."}
      ]}
    ]
  }</script>
</head>
<body></body>
</html>
"""


class _MockResponse:
    def __init__(self, text: str):
        self.text = text
        self.headers = {"Content-Type": "text/html; charset=UTF-8"}

    def raise_for_status(self):
        return None


class RecipeParsingRegressionTests(unittest.TestCase):
    def test_wprm_dom_extract_preserves_main_instructions_before_named_groups(self):
        instruction_groups = _extract_wprm_instruction_groups(OH_SNAP_BIG_MAC_BOWLS_WPRM_HTML)
        self.assertEqual(
            [group.get("title") for group in instruction_groups],
            ["Instructions", "Bowl Assembly", "Meal Prep Assembly"],
        )
        self.assertEqual(len(instruction_groups[0].get("steps") or []), 4)
        self.assertTrue((instruction_groups[0].get("steps") or [])[0].startswith("Spray a large skillet"))

    @patch("backend.app.main.requests.get")
    def test_sugarspunrun_fixture_prefers_jsonld_and_filters_dom_noise(self, mock_get):
        mock_get.return_value = _MockResponse(SUGARSPUNRUN_CHEESECAKE_FIXTURE_HTML)

        parsed = fetch_recipe_data_from_url("https://sugarspunrun.com/best-cheesecake-recipe/")

        self.assertEqual(parsed.get("title"), "The BEST Cheesecake Recipe")
        self.assertEqual(parsed.get("_selected_source"), "jsonld")

        ingredients = parsed.get("ingredients") or []
        self.assertGreaterEqual(len(ingredients), 4)
        self.assertIn("32 oz cream cheese", ingredients)
        self.assertIn("4 large eggs", ingredients)

        bad_snippets = (
            "sign up for free daily recipes",
            "recipe index",
            "from 3472 votes",
            "affiliate links",
            "published jan 30, 2019",
            "comments",
            "today i'm excited to show you",
        )

        lowered_ingredients = "\n".join(ingredients).lower()
        for snippet in bad_snippets:
            self.assertNotIn(snippet, lowered_ingredients)

    @patch("backend.app.main.requests.get")
    def test_prefers_wprm_when_grouped_structure_is_richer_than_jsonld(self, mock_get):
        mock_get.return_value = _MockResponse(FLAT_JSONLD_STRUCTURED_DOM_FIXTURE_HTML)
        dom_data = {
            "prep_time": "",
            "cook_time": "",
            "total_time": "",
            "ingredient_groups": [
                {"title": "Sauce", "items": ["1/2 cup mayo"]},
                {"title": "Beef", "items": ["1 lb lean ground beef"]},
                {"title": "Bowl Assembly", "items": ["2 cups chopped lettuce"]},
                {"title": "Meal Prep Assembly", "items": ["4 meal prep containers"]},
            ],
            "instruction_groups": [
                {"title": "Main", "steps": ["Cook beef and season."]},
                {"title": "Bowl Assembly", "steps": ["Layer lettuce, beef, and toppings."]},
                {"title": "Meal Prep Assembly", "steps": ["Pack ingredients into containers."]},
            ],
            "instruction_source": "wprm",
        }
        with patch("backend.app.main._extract_dom_recipe_data", return_value=dom_data):
            parsed = fetch_recipe_data_from_url("https://ohsnapmacros.com/big-mac-bowls/")

        self.assertEqual(parsed.get("_selected_source"), "wprm")
        self.assertEqual(parsed.get("_selected_reason"), "wprm-richer-structure")
        self.assertEqual(len(parsed.get("ingredient_groups") or []), 4)
        self.assertEqual(len(parsed.get("instruction_groups") or []), 3)

        instruction_group_titles = [group.get("title") for group in (parsed.get("instruction_groups") or []) if isinstance(group, dict)]
        self.assertIn("Bowl Assembly", instruction_group_titles)
        self.assertIn("Meal Prep Assembly", instruction_group_titles)

    @patch("backend.app.main.requests.get")
    def test_preserves_unnamed_instruction_group_steps(self, mock_get):
        mock_get.return_value = _MockResponse(OH_SNAP_BIG_MAC_BOWLS_FIXTURE_HTML)
        dom_data = {
            "prep_time": "",
            "cook_time": "",
            "total_time": "",
            "ingredient_groups": [
                {"title": "Sauce", "items": ["1/2 cup mayo"]},
            ],
            "instruction_groups": [
                {
                    "title": "",
                    "steps": [
                        "Brown the beef in a large skillet.",
                        "Drain excess grease and season beef.",
                        "Whisk together all sauce ingredients.",
                        "Set out toppings for assembly.",
                    ],
                },
                {"title": "Bowl Assembly", "steps": ["Layer lettuce, beef, and toppings."]},
                {"title": "Meal Prep Assembly", "steps": ["Pack ingredients into containers."]},
            ],
            "instruction_source": "wprm",
        }
        with patch("backend.app.main._extract_dom_recipe_data", return_value=dom_data):
            parsed = fetch_recipe_data_from_url("https://ohsnapmacros.com/big-mac-bowls/")

        instruction_groups = parsed.get("instruction_groups") or []
        instructions = parsed.get("instructions") or []
        self.assertEqual(len(instruction_groups), 3)
        self.assertEqual(instruction_groups[0].get("title"), "Instructions")
        self.assertEqual(len(instructions), 6)
        self.assertEqual(
            instructions[:4],
            [
                "Brown the beef in a large skillet.",
                "Drain excess grease and season beef.",
                "Whisk together all sauce ingredients.",
                "Set out toppings for assembly.",
            ],
        )

    @patch("backend.app.main.requests.get")
    def test_removes_group_titles_when_they_appear_as_short_steps(self, mock_get):
        mock_get.return_value = _MockResponse(OH_SNAP_BIG_MAC_BOWLS_FIXTURE_HTML)
        dom_data = {
            "prep_time": "",
            "cook_time": "",
            "total_time": "",
            "ingredient_groups": [{"title": "Main", "items": ["1 lb ground beef"]}],
            "instruction_groups": [
                {
                    "title": "Instructions",
                    "steps": ["Bowl Assembly", "Fill each bowl..."],
                },
                {
                    "title": "Bowl Assembly",
                    "steps": ["Meal Prep Assembly", "Layer meat..."],
                },
                {
                    "title": "Meal Prep Assembly",
                    "steps": ["Serve"],
                },
            ],
            "instruction_source": "wprm",
        }
        with patch("backend.app.main._extract_dom_recipe_data", return_value=dom_data):
            parsed = fetch_recipe_data_from_url("https://ohsnapmacros.com/big-mac-bowls/")

        instructions = parsed.get("instructions") or []
        self.assertEqual(instructions, ["Fill each bowl...", "Layer meat...", "Serve"])
        self.assertNotIn("Bowl Assembly", instructions)
        self.assertNotIn("Meal Prep Assembly", instructions)

    @patch("backend.app.main.requests.get")
    def test_jsonld_metadata_with_dom_group_structure_override(self, mock_get):
        mock_get.return_value = _MockResponse(FLAT_JSONLD_STRUCTURED_DOM_FIXTURE_HTML)
        dom_data = {
            "prep_time": "",
            "cook_time": "",
            "total_time": "",
            "ingredient_groups": [
                {"title": "Ingredients", "items": ["1 lb ground beef"]},
                {"title": "Big Mac Sauce", "items": ["1/2 cup mayo"]},
                {"title": "For Your Bowls", "items": ["8 cups chopped lettuce"]},
                {"title": "Optional Toppings", "items": ["Diced onions"]},
            ],
            "instruction_groups": [
                {"title": "Instructions", "steps": ["Cook beef and season."]},
                {"title": "Bowl Assembly", "steps": ["Layer lettuce, beef, and toppings."]},
                {"title": "Meal Prep Assembly", "steps": ["Pack ingredients into containers."]},
            ],
            "instruction_source": "dom",
        }
        with patch("backend.app.main._extract_dom_recipe_data", return_value=dom_data):
            parsed = fetch_recipe_data_from_url("https://example.com/big-mac-bowls/")

        self.assertEqual(parsed.get("_selected_source"), "jsonld")
        self.assertEqual(parsed.get("title"), "Big Mac Bowls")
        self.assertEqual(parsed.get("servings"), "4 bowls")
        self.assertEqual(parsed.get("prep_time"), "15 minutes")
        self.assertEqual(parsed.get("cook_time"), "20 minutes")
        self.assertEqual(parsed.get("total_time"), "35 minutes")
        self.assertEqual(parsed.get("image_url"), "https://example.com/big-mac-bowls.jpg")

        ingredient_groups = parsed.get("ingredient_groups") or []
        instruction_groups = parsed.get("instruction_groups") or []
        self.assertEqual(len(ingredient_groups), 4)
        self.assertEqual(len(instruction_groups), 4)
        self.assertEqual(ingredient_groups[1].get("title"), "Big Mac Sauce")
        self.assertEqual(instruction_groups[1].get("title"), "Instructions")
        self.assertEqual(instruction_groups[2].get("title"), "Bowl Assembly")


    @patch("backend.app.main.requests.get")
    def test_big_mac_bowls_keeps_main_instructions_group_when_flat_and_grouped_exist(self, mock_get):
        html = """
        <html><head>
        <script type="application/ld+json">{
          "@context": "https://schema.org",
          "@type": "Recipe",
          "name": "Big Mac Bowls",
          "recipeInstructions": [
            "Spray skillet and cook beef/onion.",
            "Mix sauce."
          ]
        }</script>
        </head><body></body></html>
        """
        mock_get.return_value = _MockResponse(html)
        dom_data = {
            "prep_time": "",
            "cook_time": "",
            "total_time": "",
            "ingredient_groups": [{"title": "Ingredients", "items": ["1 lb lean ground beef"]}],
            "instruction_groups": [
                {"title": "Bowl Assembly", "steps": ["Fill each bowl with lettuce and toppings."]},
                {"title": "Meal Prep Assembly", "steps": ["Layer ingredients into containers."]},
            ],
            "instruction_source": "dom",
        }
        with patch("backend.app.main._extract_dom_recipe_data", return_value=dom_data):
            parsed = fetch_recipe_data_from_url("https://example.com/big-mac-bowls/")

        instruction_groups = parsed.get("instruction_groups") or []
        instructions = parsed.get("instructions") or []

        self.assertEqual(len(instruction_groups), 3)
        self.assertIn(instruction_groups[0].get("title"), {"Instructions", "Main Instructions"})
        self.assertGreaterEqual(len(instruction_groups[0].get("steps") or []), 2)
        self.assertGreaterEqual(len(instructions), 4)

        titles = [group.get("title") for group in instruction_groups if isinstance(group, dict)]
        self.assertIn("Bowl Assembly", titles)
        self.assertIn("Meal Prep Assembly", titles)

    @patch("backend.app.main.requests.get")
    def test_big_mac_bowls_prefers_full_jsonld_before_ai_cleanup(self, mock_get):
        mock_get.return_value = _MockResponse(BIG_MAC_BOWLS_FULL_JSONLD_FIXTURE_HTML)
        dom_data = {
            "prep_time": "",
            "cook_time": "",
            "total_time": "",
            "ingredient_groups": [
                {"title": "Ingredients", "items": ["1 lb lean ground beef"]},
                {"title": "Sauce", "items": ["1/2 cup mayonnaise"]},
            ],
            "instruction_groups": [
                {"title": "Instructions", "steps": ["Brown beef.", "Mix sauce."]},
            ],
            "instruction_source": "dom",
        }
        with patch("backend.app.main._extract_dom_recipe_data", return_value=dom_data):
            parsed = fetch_recipe_data_from_url("https://ohsnapmacros.com/big-mac-bowls/")

        self.assertEqual(parsed.get("_selected_source"), "jsonld")
        self.assertGreaterEqual(len(parsed.get("ingredients") or []), 17)
        self.assertGreaterEqual(len(parsed.get("instructions") or []), 6)
        self.assertEqual(len(parsed.get("instruction_groups") or []), 3)


if __name__ == "__main__":
    unittest.main()
