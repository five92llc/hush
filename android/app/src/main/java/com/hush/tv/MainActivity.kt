package com.hush.tv

import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.app.ProgressDialog
import android.app.UiModeManager
import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import kotlin.concurrent.thread

/** Hush on a TV or tablet: the Hush web app full screen, plus a server address, remote keys and self-update. */
class MainActivity : Activity() {
    private lateinit var root: FrameLayout
    private lateinit var web: WebView
    private var customView: View? = null
    private var customCallback: WebChromeClient.CustomViewCallback? = null
    private var errorView: View? = null
    private var lastBack = 0L
    private var loadFailed = false

    private val prefs by lazy { getSharedPreferences("hush", Context.MODE_PRIVATE) }
    private val isTv: Boolean
        get() = (getSystemService(Context.UI_MODE_SERVICE) as UiModeManager).currentModeType == Configuration.UI_MODE_TYPE_TELEVISION ||
            packageManager.hasSystemFeature("amazon.hardware.fire_tv") || packageManager.hasSystemFeature("android.software.leanback")

    @SuppressLint("SetJavaScriptEnabled", "AddJavascriptInterface")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        root = FrameLayout(this).apply { setBackgroundColor(Color.parseColor("#191A2C")) }
        setContentView(root)

        web = WebView(this).apply {
            setBackgroundColor(Color.parseColor("#191A2C"))
            isFocusable = true; isFocusableInTouchMode = true
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                mediaPlaybackRequiresUserGesture = false
                mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                useWideViewPort = true; loadWithOverviewMode = true
                cacheMode = WebSettings.LOAD_DEFAULT
                // Hush looks for these words to switch itself into big screen mode and use the remote's keys.
                userAgentString = "$userAgentString HushApp/${BuildConfig.VERSION_NAME}" + if (isTv) " HushTV" else ""
            }
            addJavascriptInterface(Bridge(), "HushApp")
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView, url: String) { if (!loadFailed) hideError() }
                override fun onReceivedError(view: WebView, req: WebResourceRequest, err: WebResourceError) {
                    if (req.isForMainFrame) { loadFailed = true; showError("Could not reach Hush at ${server()}.") }
                }
                override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean = false
            }
            webChromeClient = object : WebChromeClient() {
                override fun onShowCustomView(view: View, cb: CustomViewCallback) {     // the page asked for full screen
                    customView = view; customCallback = cb
                    root.addView(view, ViewGroup.LayoutParams(-1, -1))
                }
                override fun onHideCustomView() { leaveCustomView() }
            }
        }
        root.addView(web, ViewGroup.LayoutParams(-1, -1))
        goImmersive()
        if (server().isEmpty()) askServer(first = true) else load()
        maybeCheckForUpdate()
    }

    // ---------- server address ----------
    private fun server(): String = prefs.getString("server", "") ?: ""

    private fun load() {
        loadFailed = false
        web.loadUrl(server())
    }

    private fun askServer(first: Boolean = false) {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_TEXT_VARIATION_URI
            setText(prefs.getString("server_try", null) ?: server().ifEmpty { "http://hush.local" })
            setSelectAllOnFocus(true)
            setSingleLine()
        }
        AlertDialog.Builder(this)
            .setTitle(if (first) "Welcome to Hush" else "Hush server")
            .setMessage("Type the address of your Hush server, for example http://192.168.100.228 or http://hush.local")
            .setView(input)
            .setCancelable(!first)
            .setPositiveButton("Connect") { _, _ ->
                var url = input.text.toString().trim().trimEnd('/')
                if (url.isNotEmpty()) {
                    if (!url.startsWith("http://") && !url.startsWith("https://")) url = "http://$url"
                    verifyServer(url, first)
                } else if (first) askServer(true)
            }
            .setNegativeButton(if (first) "Quit" else "Cancel") { _, _ -> if (first) finish() }
            .show()
    }

    /** Checks that a Hush server answers at this address before saving it, so a typo is caught straight away. */
    private fun verifyServer(url: String, first: Boolean) {
        Toast.makeText(this, "Checking $url…", Toast.LENGTH_SHORT).show()
        thread {
            val ok = try {
                val c = java.net.URL("$url/api/session").openConnection() as java.net.HttpURLConnection
                c.connectTimeout = 6000; c.readTimeout = 6000
                c.inputStream.bufferedReader().use { it.readText() }.contains("auth_required")
            } catch (e: Exception) { false }
            runOnUiThread {
                if (ok) { prefs.edit().putString("server", url).apply(); hideError(); load() }
                else {
                    Toast.makeText(this, "No Hush server answered at $url. Check the address and that this device is on the same network.", Toast.LENGTH_LONG).show()
                    prefs.edit().putString("server_try", url).apply()
                    askServer(first)
                }
            }
        }
    }

    // ---------- an error page with ways out ----------
    private fun showError(message: String) {
        hideError()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor("#191A2C")); setPadding(60, 60, 60, 60)
        }
        box.addView(TextView(this).apply { text = message; setTextColor(Color.WHITE); textSize = 22f; gravity = Gravity.CENTER })
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER; setPadding(0, 40, 0, 0) }
        val retry = Button(this).apply { text = "Try again"; setOnClickListener { load() } }
        val change = Button(this).apply { text = "Change server"; setOnClickListener { askServer() } }
        row.addView(retry); row.addView(change)
        box.addView(row)
        root.addView(box, ViewGroup.LayoutParams(-1, -1))
        errorView = box
        retry.requestFocus()
    }

    private fun hideError() { errorView?.let { root.removeView(it) }; errorView = null }

    // ---------- keys ----------
    private fun js(code: String, cb: ((String) -> Unit)? = null) = web.evaluateJavascript(code) { cb?.invoke(it ?: "") }

    private fun sendKey(key: String, code: Int) = js(
        "document.dispatchEvent(new KeyboardEvent('keydown',{key:'$key',keyCode:$code,which:$code,bubbles:true,cancelable:true}))")

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (customView != null && keyCode == KeyEvent.KEYCODE_BACK) { leaveCustomView(); return true }
        when (keyCode) {
            KeyEvent.KEYCODE_BACK -> { onBack(); return true }
            KeyEvent.KEYCODE_MENU -> { showMenu(); return true }
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.KEYCODE_MEDIA_PLAY, KeyEvent.KEYCODE_MEDIA_PAUSE -> { sendKey("MediaPlayPause", 179); return true }
            KeyEvent.KEYCODE_MEDIA_STOP -> { sendKey("MediaStop", 178); return true }
            KeyEvent.KEYCODE_MEDIA_NEXT -> { sendKey("MediaTrackNext", 176); return true }
            KeyEvent.KEYCODE_MEDIA_PREVIOUS -> { sendKey("MediaTrackPrevious", 177); return true }
            KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> { sendKey("MediaFastForward", 228); return true }
            KeyEvent.KEYCODE_MEDIA_REWIND -> { sendKey("MediaRewind", 227); return true }
            KeyEvent.KEYCODE_CHANNEL_UP -> { sendKey("ChannelUp", 427); return true }
            KeyEvent.KEYCODE_CHANNEL_DOWN -> { sendKey("ChannelDown", 428); return true }
        }
        return super.onKeyDown(keyCode, event)
    }

    /** Back steps out of whatever Hush shows; on the home page it asks to press again before leaving. */
    private fun onBack() {
        if (errorView != null || server().isEmpty()) { finish(); return }
        js("(function(){var p=document.getElementById('player');var d=document.querySelector('dialog[open]');" +
            "var home=!location.hash||location.hash==='#/home'||location.hash==='#/';" +
            "return JSON.stringify({home:home,busy:!!d||!!(p&&!p.hidden)});})()") { r ->
            val home = r.contains("\\\"home\\\":true")
            val busy = r.contains("\\\"busy\\\":true")
            if (home && !busy) {
                val now = System.currentTimeMillis()
                if (now - lastBack < 2000) finish() else { lastBack = now; Toast.makeText(this, "Press Back again to leave Hush", Toast.LENGTH_SHORT).show() }
            } else sendKey("Escape", 27)
        }
    }

    private fun showMenu() {
        val items = arrayOf("Change server", "Check for updates", "Reload", "About")
        AlertDialog.Builder(this).setTitle("Hush app").setItems(items) { _, i ->
            when (i) {
                0 -> askServer()
                1 -> checkForUpdate(manual = true)
                2 -> load()
                3 -> Toast.makeText(this, "Hush app ${BuildConfig.VERSION_NAME} · ${server()}", Toast.LENGTH_LONG).show()
            }
        }.show()
    }

    // ---------- immersive full screen ----------
    @Suppress("DEPRECATION")
    private fun goImmersive() {
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_FULLSCREEN or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) { super.onWindowFocusChanged(hasFocus); if (hasFocus) goImmersive() }

    private fun leaveCustomView() {
        customView?.let { root.removeView(it) }
        customView = null; customCallback?.onCustomViewHidden(); customCallback = null
        web.requestFocus()
    }

    override fun onResume() { super.onResume(); web.onResume(); web.requestFocus() }
    override fun onPause() { web.onPause(); super.onPause() }
    override fun onDestroy() { web.destroy(); super.onDestroy() }

    // ---------- updates ----------
    private fun maybeCheckForUpdate() {
        val last = prefs.getLong("lastCheck", 0)
        if (System.currentTimeMillis() - last > 6 * 3600_000L) checkForUpdate(manual = false)
    }

    private fun checkForUpdate(manual: Boolean) {
        thread {
            val rel = try { Updater.check() } catch (e: Exception) {
                if (manual) runOnUiThread { Toast.makeText(this, "Could not check for updates: ${e.message}", Toast.LENGTH_LONG).show() }
                return@thread
            }
            prefs.edit().putLong("lastCheck", System.currentTimeMillis()).apply()
            runOnUiThread {
                if (rel == null) { if (manual) Toast.makeText(this, "Hush ${BuildConfig.VERSION_NAME} is the latest version", Toast.LENGTH_LONG).show() }
                else offerUpdate(rel)
            }
        }
    }

    private fun offerUpdate(rel: Release) {
        if (isFinishing) return
        AlertDialog.Builder(this).setTitle("Hush ${rel.version} is available")
            .setMessage(rel.notes.ifEmpty { "A new version of the Hush app is ready." } + "\n\nYou have ${BuildConfig.VERSION_NAME}.")
            .setPositiveButton("Update now") { _, _ -> startUpdate(rel) }
            .setNegativeButton("Later", null).show()
    }

    private fun startUpdate(rel: Release) {
        if (Build.VERSION.SDK_INT >= 26 && !packageManager.canRequestPackageInstalls()) {
            AlertDialog.Builder(this).setTitle("Allow updates")
                .setMessage("Android needs your permission once for Hush to install its own updates. Turn on \"Allow from this source\" for Hush, then come back and update again.")
                .setPositiveButton("Open settings") { _, _ ->
                    try { startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName"))) }
                    catch (e: Exception) { Toast.makeText(this, "Open Settings → Apps → Special access → Install unknown apps → Hush", Toast.LENGTH_LONG).show() }
                }.setNegativeButton("Cancel", null).show()
            return
        }
        @Suppress("DEPRECATION")
        val bar = ProgressDialog(this).apply { setMessage("Downloading Hush ${rel.version}…"); setProgressStyle(ProgressDialog.STYLE_HORIZONTAL); max = 100; setCancelable(false); show() }
        thread {
            try {
                val apk = Updater.download(this, rel) { p -> runOnUiThread { bar.progress = p } }
                runOnUiThread { bar.dismiss(); Updater.install(this, apk) }
            } catch (e: Exception) {
                runOnUiThread { bar.dismiss(); Toast.makeText(this, "Update failed: ${e.message}", Toast.LENGTH_LONG).show() }
            }
        }
    }

    /** What the Hush web pages can ask the app (Settings → App in the web UI uses this). */
    inner class Bridge {
        @JavascriptInterface fun version(): String = BuildConfig.VERSION_NAME
        @JavascriptInterface fun server(): String = this@MainActivity.server()
        @JavascriptInterface fun checkForUpdate() { runOnUiThread { this@MainActivity.checkForUpdate(manual = true) } }
        @JavascriptInterface fun changeServer() { runOnUiThread { askServer() } }
    }
}
