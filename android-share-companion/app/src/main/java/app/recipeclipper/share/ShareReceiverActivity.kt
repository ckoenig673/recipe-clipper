package app.recipeclipper.share

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import androidx.browser.customtabs.CustomTabsIntent

class ShareReceiverActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleIncomingIntent(intent)
    }

    private fun handleIncomingIntent(intent: Intent?) {
        Log.d(TAG, "Incoming intent action=${intent?.action}, type=${intent?.type}, data=${intent?.dataString}")
        Log.d(TAG, "Detected share intent type=${intent?.type ?: "unknown"}")

        val payload = extractSharedPayload(intent)
        Log.d(TAG, "Detected URL=${if (payload.url.isNullOrBlank()) "no" else "yes"}")
        Log.d(
            TAG,
            "Payload summary: hasUrl=${payload.url != null}, hasTitle=${payload.title != null}, hasText=${payload.text != null}, textLength=${payload.text?.length ?: 0}"
        )

        val params = linkedMapOf<String, String>()
        payload.url?.let { params["url"] = it }
        payload.title?.let { params["title"] = it }
        payload.text?.let { params["text"] = it }

        val finalUrl = buildTargetUrl(
            baseUrl = Config.WEB_APP_BASE_URL,
            path = Config.SHARE_PATH,
            params = params
        )
        Log.d(TAG, "Final launch URL=$finalUrl")

        val uri = Uri.parse(finalUrl)
        val customTabsIntent = CustomTabsIntent.Builder().build()
        customTabsIntent.intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

        try {
            customTabsIntent.launchUrl(this, uri)
        } catch (_: Exception) {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } finally {
            finish()
        }
    }

    private fun extractSharedPayload(intent: Intent?): SharedPayload {
        if (intent == null) return SharedPayload()

        val url = extractBestUrl(intent)
        val title = extractBestTitle(intent)
        val text = extractBestText(intent)

        return SharedPayload(
            url = url?.takeIf { it.isNotBlank() },
            title = title?.takeIf { it.isNotBlank() },
            text = text?.takeIf { it.isNotBlank() }
        )
    }

    private fun extractBestUrl(intent: Intent): String? {
        val sources = mutableListOf<String>()

        intent.getStringExtra(Intent.EXTRA_TEXT)
            ?.trim()
            ?.takeIf { it.isNotBlank() }
            ?.let {
                Log.d(TAG, "Raw EXTRA_TEXT payload=$it")
                sources += it
            }

        intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)
            ?.toString()
            ?.trim()
            ?.takeIf { it.isNotBlank() }
            ?.let {
                Log.d(TAG, "Raw EXTRA_PROCESS_TEXT payload=$it")
                sources += it
            }

        intent.dataString
            ?.trim()
            ?.takeIf { it.isNotBlank() }
            ?.let {
                Log.d(TAG, "Raw intent dataString payload=$it")
                sources += it
            }

        val clipData = intent.clipData
        if (clipData != null) {
            for (i in 0 until clipData.itemCount) {
                val item = clipData.getItemAt(i)

                item.text
                    ?.toString()
                    ?.trim()
                    ?.takeIf { it.isNotBlank() }
                    ?.let {
                        Log.d(TAG, "Raw ClipData[$i] text payload=$it")
                        sources += it
                    }

                item.uri
                    ?.toString()
                    ?.trim()
                    ?.takeIf { it.isNotBlank() }
                    ?.let {
                        Log.d(TAG, "Raw ClipData[$i] uri payload=$it")
                        sources += it
                    }

                item.intent
                    ?.dataString
                    ?.trim()
                    ?.takeIf { it.isNotBlank() }
                    ?.let {
                        Log.d(TAG, "Raw ClipData[$i] intent.data payload=$it")
                        sources += it
                    }
            }
        }

        val extraStream = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
        if (extraStream != null) {
            Log.d(TAG, "EXTRA_STREAM present=$extraStream (ignored as URL source)")
        }

        val allCandidates = mutableListOf<String>()
        for (source in sources) {
            allCandidates += findAllUrls(source)
        }

        if (allCandidates.isEmpty()) {
            Log.d(TAG, "No URL candidates found in shared payload")
            return null
        }

        Log.d(TAG, "Extracted URL candidates=$allCandidates")

        val nonFacebookExternal = allCandidates.firstOrNull { !isFacebookInternalUrl(it) }
        if (nonFacebookExternal != null) {
            Log.d(TAG, "Selected non-Facebook URL candidate=$nonFacebookExternal")
            return nonFacebookExternal
        }

        val fallback = allCandidates.firstOrNull()
        Log.d(TAG, "Falling back to first URL candidate=$fallback")
        return fallback
    }

    private fun findAllUrls(text: String): List<String> {
        val urlRegex = Regex("https?://[^\\s\\\"'<>]+", RegexOption.IGNORE_CASE)
        return urlRegex.findAll(text)
            .mapNotNull { match ->
                val rawMatch = match.value
                Log.d(TAG, "Extracted URL match=$rawMatch")
                normalizeSharedUrl(rawMatch)
            }
            .filter { isHttpUrl(it) }
            .toList()
    }

    private fun normalizeSharedUrl(rawUrl: String): String? {
        val sanitized = sanitizeUrl(rawUrl)
        if (!isHttpUrl(sanitized)) return null
        Log.d(TAG, "Normalized URL after sanitization=$sanitized")

        val decodedFacebookUrl = decodeFacebookRedirectUrl(sanitized)
        if (decodedFacebookUrl != null) {
            Log.d(TAG, "Using decoded Facebook redirect URL=$decodedFacebookUrl")
            return decodedFacebookUrl
        }

        return sanitized
    }

    private fun decodeFacebookRedirectUrl(url: String): String? {
        val uri = Uri.parse(url)
        val host = uri.host?.lowercase() ?: return null
        val isFacebookRedirectHost = host == "l.facebook.com" || host == "lm.facebook.com"
        val isRedirectPath = uri.path?.startsWith("/l.php") == true

        if (!isFacebookRedirectHost || !isRedirectPath) return null

        val encodedTarget = uri.getQueryParameter("u")?.trim()
        if (encodedTarget.isNullOrBlank()) return null

        val decodedTarget = Uri.decode(encodedTarget)
        val sanitizedTarget = sanitizeUrl(decodedTarget)
        Log.d(TAG, "Facebook redirect detected, encoded u=$encodedTarget, decoded u=$sanitizedTarget")

        return sanitizedTarget.takeIf { isHttpUrl(it) }
    }

    private fun extractBestTitle(intent: Intent): String? {
        return listOf(
            intent.getStringExtra(Intent.EXTRA_SUBJECT),
            intent.getStringExtra(Intent.EXTRA_TITLE)
        )
            .firstOrNull { !it.isNullOrBlank() }
            ?.trim()
    }

    private fun extractBestText(intent: Intent): String? {
        return listOf(
            intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)?.toString(),
            intent.getStringExtra(Intent.EXTRA_TEXT)
        )
            .firstOrNull { !it.isNullOrBlank() }
            ?.trim()
    }

    private fun buildTargetUrl(baseUrl: String, path: String, params: Map<String, String>): String {
        val normalizedBase = baseUrl.trimEnd('/')
        val normalizedPath = if (path.startsWith("/")) path else "/$path"
        val uriBuilder = Uri.parse("$normalizedBase$normalizedPath").buildUpon()

        params.forEach { (key, value) ->
            uriBuilder.appendQueryParameter(key, value)
        }

        return uriBuilder.build().toString()
    }

    private fun sanitizeUrl(url: String): String {
        return url
            .trim()
            .removeSuffix(")")
            .removeSuffix("]")
            .removeSuffix("}")
            .removeSuffix(",")
            .removeSuffix(".")
            .removeSuffix(";")
    }

    private fun isHttpUrl(value: String): Boolean {
        val uri = Uri.parse(value)
        val scheme = uri.scheme?.lowercase()
        return scheme == "http" || scheme == "https"
    }

    private fun isFacebookInternalUrl(value: String): Boolean {
        val uri = Uri.parse(value)
        val host = uri.host?.lowercase() ?: return false
        return host == "facebook.com" ||
            host.endsWith(".facebook.com") ||
            host == "fb.com" ||
            host.endsWith(".fb.com")
    }

    private data class SharedPayload(
        val url: String? = null,
        val title: String? = null,
        val text: String? = null
    )

    companion object {
        private const val TAG = "ShareReceiverActivity"
    }
}
