package com.hush.tv

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.os.Build
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** What a newer release offers. */
data class Release(val version: String, val apkUrl: String, val sha256: String?, val notes: String)

/**
 * Finds newer releases of this app on GitHub and installs them.
 *
 * A release is a tag `android-v<version>` with an APK attached (named `hush-tv-<version>.apk`).
 * Android asks for one confirmation per update; it does not allow an app to replace itself silently.
 */
object Updater {
    const val REPO = "five92llc/hush"

    /** The newest release if it is newer than this app, else null. Throws when GitHub cannot be reached. */
    fun check(): Release? {
        val json = get("https://api.github.com/repos/$REPO/releases?per_page=20")
        val list = org.json.JSONArray(json)
        var best: Release? = null
        for (i in 0 until list.length()) {
            val r = list.getJSONObject(i)
            if (r.optBoolean("draft") || r.optBoolean("prerelease")) continue
            val tag = r.optString("tag_name")
            if (!tag.startsWith("android-v")) continue
            val version = tag.removePrefix("android-v")
            val apk = (0 until r.getJSONArray("assets").length()).map { r.getJSONArray("assets").getJSONObject(it) }
                .firstOrNull { it.optString("name").endsWith(".apk") } ?: continue
            val digest = apk.optString("digest").removePrefix("sha256:").ifEmpty { null }
            val rel = Release(version, apk.getString("browser_download_url"), digest, r.optString("body").take(400))
            if (best == null || compare(version, best.version) > 0) best = rel
        }
        return best?.takeIf { compare(it.version, BuildConfig.VERSION_NAME) > 0 }
    }

    fun compare(a: String, b: String): Int {
        val x = a.split(".").map { it.toIntOrNull() ?: 0 }
        val y = b.split(".").map { it.toIntOrNull() ?: 0 }
        for (i in 0 until maxOf(x.size, y.size)) {
            val d = x.getOrElse(i) { 0 } - y.getOrElse(i) { 0 }
            if (d != 0) return d
        }
        return 0
    }

    /** Downloads the APK into the app's cache. [progress] gets 0..100 on a background thread. */
    fun download(ctx: Context, rel: Release, progress: (Int) -> Unit): File {
        val dir = File(ctx.cacheDir, "updates").apply { mkdirs(); listFiles()?.forEach { it.delete() } }
        val out = File(dir, "hush-tv-${rel.version}.apk")
        val conn = open(rel.apkUrl)
        val total = conn.contentLengthLong
        val md = MessageDigest.getInstance("SHA-256")
        conn.inputStream.use { input ->
            out.outputStream().use { sink ->
                val buf = ByteArray(64 * 1024)
                var done = 0L
                while (true) {
                    val n = input.read(buf)
                    if (n < 0) break
                    sink.write(buf, 0, n); md.update(buf, 0, n); done += n
                    if (total > 0) progress((done * 100 / total).toInt())
                }
            }
        }
        val got = md.digest().joinToString("") { "%02x".format(it) }
        if (rel.sha256 != null && !got.equals(rel.sha256, ignoreCase = true)) {
            out.delete()
            throw IllegalStateException("The download did not match its checksum")
        }
        return out
    }

    /** Hands the APK to Android's installer; the system shows its own "Install?" screen. */
    fun install(ctx: Context, apk: File) {
        val installer = ctx.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        val id = installer.createSession(params)
        installer.openSession(id).use { session ->
            apk.inputStream().use { input -> session.openWrite("hush", 0, apk.length()).use { out -> input.copyTo(out); session.fsync(out) } }
            val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
            val pi = PendingIntent.getBroadcast(ctx, id, Intent(ctx, InstallReceiver::class.java), flags)
            session.commit(pi.intentSender)
        }
    }

    private fun open(url: String): HttpURLConnection {
        var u = url
        repeat(5) {
            val c = URL(u).openConnection() as HttpURLConnection
            c.connectTimeout = 15000; c.readTimeout = 30000; c.instanceFollowRedirects = false
            c.setRequestProperty("User-Agent", "HushTV/${BuildConfig.VERSION_NAME}")
            c.setRequestProperty("Accept", "application/vnd.github+json, application/octet-stream")
            if (c.responseCode in 301..308) { u = URL(URL(u), c.getHeaderField("Location")).toString(); c.disconnect(); return@repeat }
            if (c.responseCode !in 200..299) throw IllegalStateException("GitHub answered ${c.responseCode}")
            return c
        }
        throw IllegalStateException("Too many redirects")
    }

    private fun get(url: String): String = open(url).inputStream.bufferedReader().use { it.readText() }
}

/** Receives the installer's progress; when Android needs the person to confirm, this opens its screen. */
class InstallReceiver : android.content.BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -1)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION")
                val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                confirm?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                if (confirm != null) ctx.startActivity(confirm)
            }
            PackageInstaller.STATUS_SUCCESS -> {}
            else -> android.widget.Toast.makeText(ctx, "The update could not be installed: " +
                (intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: "unknown reason"), android.widget.Toast.LENGTH_LONG).show()
        }
    }
}
