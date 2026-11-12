package app.recipeclipper.share

import android.net.Uri

object Config {
    private const val DEFAULT_PLACEHOLDER_HOST = "recipe-clipper.invalid"
    private const val BASE_URL_PROPERTY_NAME = "recipeClipperBaseUrl"

    const val SHARE_PATH = "/"

    val webAppBaseUri: Uri = parseBaseUri(BuildConfig.RECIPE_CLIPPER_BASE_URL)

    private fun parseBaseUri(rawValue: String): Uri {
        val trimmed = rawValue.trim()
        require(trimmed.isNotBlank()) {
            "Recipe Clipper base URL is blank. Set the Gradle property '$BASE_URL_PROPERTY_NAME'."
        }

        val uri = Uri.parse(trimmed)
        val scheme = uri.scheme?.lowercase()

        require(scheme == "http" || scheme == "https") {
            "Recipe Clipper base URL must use http or https. Current value: '$trimmed'."
        }
        require(!uri.host.isNullOrBlank()) {
            "Recipe Clipper base URL must include a host. Current value: '$trimmed'."
        }
        require(uri.query == null && uri.fragment == null) {
            "Recipe Clipper base URL must not include a query string or fragment. Current value: '$trimmed'."
        }
        require(!uri.host.equals(DEFAULT_PLACEHOLDER_HOST, ignoreCase = true)) {
            "Recipe Clipper base URL is still the checked-in placeholder. Set the Gradle property '$BASE_URL_PROPERTY_NAME' to your deployed web app URL."
        }

        return uri
    }
}
