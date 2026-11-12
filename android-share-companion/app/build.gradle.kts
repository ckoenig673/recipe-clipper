plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

import java.net.URI

val recipeClipperBaseUrlProperty = "recipeClipperBaseUrl"
val defaultRecipeClipperBaseUrl = "https://recipe-clipper.invalid"
val recipeClipperBaseUrl = providers
    .gradleProperty(recipeClipperBaseUrlProperty)
    .orElse(defaultRecipeClipperBaseUrl)
    .get()
    .trim()

fun String.toBuildConfigString(): String = buildString {
    append('"')
    for (char in this@toBuildConfigString) {
        when (char) {
            '\\' -> append("\\\\")
            '"' -> append("\\\"")
            else -> append(char)
        }
    }
    append('"')
}

fun validateRecipeClipperBaseUrl(rawValue: String) {
    require(rawValue.isNotBlank()) {
        "The Gradle property '$recipeClipperBaseUrlProperty' must not be blank."
    }

    val parsed = try {
        URI(rawValue)
    } catch (error: Exception) {
        throw GradleException(
            "The Gradle property '$recipeClipperBaseUrlProperty' must be a valid absolute http(s) URL.",
            error
        )
    }

    require(parsed.isAbsolute && !parsed.host.isNullOrBlank()) {
        "The Gradle property '$recipeClipperBaseUrlProperty' must be a valid absolute http(s) URL."
    }
    require(parsed.scheme == "http" || parsed.scheme == "https") {
        "The Gradle property '$recipeClipperBaseUrlProperty' must use http or https."
    }
    require(parsed.rawQuery == null && parsed.rawFragment == null) {
        "The Gradle property '$recipeClipperBaseUrlProperty' must not include a query string or fragment."
    }
}

validateRecipeClipperBaseUrl(recipeClipperBaseUrl)

android {
    namespace = "app.recipeclipper.share"
    compileSdk = 34

    defaultConfig {
        applicationId = "app.recipeclipper.share"
        minSdk = 26
        targetSdk = 34
        versionCode = 2
        versionName = "0.2.1"
        buildConfigField(
            "String",
            "RECIPE_CLIPPER_BASE_URL",
            recipeClipperBaseUrl.toBuildConfigString()
        )
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.browser:browser:1.8.0")
}
