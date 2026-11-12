Recipe Clipper Android Share Companion

Provide the Recipe Clipper web app base URL with the Gradle property `recipeClipperBaseUrl`.

Examples:
- `./gradlew assembleDebug -PrecipeClipperBaseUrl=https://recipes.example.com`
- Add `recipeClipperBaseUrl=https://recipes.example.com` to `~/.gradle/gradle.properties`

Requirements:
- Use the deployed Recipe Clipper web app origin, optionally including a path prefix.
- Do not include query parameters or fragments.
- The checked-in placeholder `https://recipe-clipper.invalid` is intentionally non-functional and will fail at runtime if you do not override it.

Default placeholder URL:
- https://recipe-clipper.invalid

Share launch format:
- https://recipes.example.com/?share_import=1&url=...&title=...&text=...
