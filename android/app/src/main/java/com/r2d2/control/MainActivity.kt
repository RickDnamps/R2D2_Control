package com.r2d2.control

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.Context
import android.net.wifi.WifiManager
import android.os.*
import android.text.InputType
import android.view.*
import android.webkit.*
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import com.r2d2.control.databinding.ActivityMainBinding
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var webView: WebView
    private var isServerOnline = false
    private val pingHandler = Handler(Looper.getMainLooper())

    companion object {
        const val PREF_FILE    = "r2d2_prefs"
        const val PREF_HOST    = "host"
        const val DEFAULT_HOST = "192.168.4.1"
        const val DEFAULT_PORT = 5000
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        webView = binding.webview

        // Full screen immersive
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.apply {
                hide(android.view.WindowInsets.Type.statusBars() or android.view.WindowInsets.Type.navigationBars())
                systemBarsBehavior = android.view.WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = (
                View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or
                View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            )
        }

        // Banner starts visible (offline state) — slide it above screen once measured
        binding.statusBanner.viewTreeObserver.addOnGlobalLayoutListener(object :
            android.view.ViewTreeObserver.OnGlobalLayoutListener {
            override fun onGlobalLayout() {
                binding.statusBanner.viewTreeObserver.removeOnGlobalLayoutListener(this)
                // Already offline → stay visible (translationY = 0)
            }
        })

        // IP label click → change host dialog
        binding.statusHost.setOnClickListener { showHostDialog() }

        setupWebView()
        loadDashboard()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack()
                else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView.settings.apply {
            javaScriptEnabled          = true
            domStorageEnabled          = true
            loadWithOverviewMode       = true
            useWideViewPort            = true
            setSupportZoom(false)
            builtInZoomControls        = false
            displayZoomControls        = false
            mediaPlaybackRequiresUserGesture = false
            cacheMode                  = WebSettings.LOAD_DEFAULT
            mixedContentMode           = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            allowUniversalAccessFromFileURLs = true
            allowFileAccessFromFileURLs = true
        }

        webView.addJavascriptInterface(NativeBridge(this), "AndroidBridge")

        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                binding.loadingOverlay.visibility = View.VISIBLE
            }
            override fun onPageFinished(view: WebView?, url: String?) {
                binding.loadingOverlay.visibility = View.GONE
            }
            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                if (request?.isForMainFrame == true) {
                    binding.loadingOverlay.visibility = View.GONE
                }
            }
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?) = false
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(msg: ConsoleMessage?) = true
        }
    }

    private fun loadDashboard() {
        webView.loadUrl("file:///android_asset/index.html")
        startPingLoop()
    }

    private fun startPingLoop() {
        pingHandler.removeCallbacksAndMessages(null)
        val prefs = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        val host  = prefs.getString(PREF_HOST, DEFAULT_HOST) ?: DEFAULT_HOST
        val port  = prefs.getInt("port", DEFAULT_PORT)

        // Show current host in banner immediately
        binding.statusHost.text = "$host:$port"

        pingHandler.post(object : Runnable {
            override fun run() {
                Thread {
                    val online = checkServer(host, port)
                    runOnUiThread {
                        if (online != isServerOnline) {
                            isServerOnline = online
                            updateStatusBanner(host, port, online)
                            if (online) webView.evaluateJavascript(
                                "window.R2D2_API_BASE='http://$host:$port';" +
                                "if(typeof pollStatus==='function') pollStatus();", null
                            )
                        }
                    }
                    pingHandler.postDelayed(this, if (online) 15_000L else 5_000L)
                }.start()
            }
        })
    }

    private fun checkServer(host: String, port: Int): Boolean {
        return try {
            val conn = URL("http://$host:$port/status").openConnection() as HttpURLConnection
            conn.connectTimeout = 3000
            conn.readTimeout    = 3000
            conn.requestMethod  = "GET"
            val code = conn.responseCode
            conn.disconnect()
            code in 200..299
        } catch (e: Exception) { false }
    }

    private fun updateStatusBanner(host: String, port: Int, online: Boolean) {
        binding.statusHost.text = "$host:$port"
        if (online) {
            // Slide banner UP and off screen
            val h = binding.statusBanner.height.takeIf { it > 0 }
                ?: (37 * resources.displayMetrics.density).toInt()
            binding.statusBanner.animate()
                .translationY(-h.toFloat())
                .setDuration(350)
                .withEndAction { binding.statusBanner.visibility = View.GONE }
                .start()
        } else {
            // Slide banner DOWN into view
            binding.statusBanner.visibility = View.VISIBLE
            binding.statusBanner.animate()
                .translationY(0f)
                .setDuration(350)
                .start()
            binding.statusDot.setTextColor(android.graphics.Color.parseColor("#ff2244"))
            binding.statusText.text = "HORS LIGNE"
            binding.statusText.setTextColor(android.graphics.Color.parseColor("#ff2244"))
            binding.statusHost.setTextColor(android.graphics.Color.parseColor("#00aaff"))
        }
    }

    /** Dialog natif pour changer l'adresse IP du Master. */
    private fun showHostDialog() {
        val prefs       = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        val currentHost = prefs.getString(PREF_HOST, DEFAULT_HOST) ?: DEFAULT_HOST

        val input = EditText(this).apply {
            setText(currentHost)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setTextColor(android.graphics.Color.WHITE)
            setHintTextColor(android.graphics.Color.parseColor("#556677"))
            hint = "ex: 192.168.4.1  ou  192.168.2.104"
            setSelection(text.length)
        }

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (16 * resources.displayMetrics.density).toInt()
            setPadding(pad * 2, pad, pad * 2, 0)
            addView(input)
        }

        AlertDialog.Builder(this)
            .setTitle("Adresse IP du Master R2-D2")
            .setMessage("Hotspot R2-D2: 192.168.4.1\nWiFi maison: IP locale du Pi")
            .setView(container)
            .setPositiveButton("CONNECTER") { _, _ ->
                val newHost = input.text.toString().trim()
                if (newHost.isNotBlank()) {
                    prefs.edit().putString(PREF_HOST, newHost).apply()
                    isServerOnline = false
                    // Reset banner to offline state before restarting loop
                    binding.statusBanner.clearAnimation()
                    binding.statusBanner.translationY = 0f
                    binding.statusBanner.visibility = View.VISIBLE
                    binding.statusDot.setTextColor(android.graphics.Color.parseColor("#ff2244"))
                    binding.statusText.text = "HORS LIGNE"
                    binding.statusText.setTextColor(android.graphics.Color.parseColor("#ff2244"))
                    binding.statusHost.text = "$newHost:$DEFAULT_PORT"
                    webView.evaluateJavascript(
                        "window.R2D2_API_BASE='http://$newHost:$DEFAULT_PORT';", null
                    )
                    startPingLoop()
                }
            }
            .setNegativeButton("ANNULER", null)
            .show()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                window.insetsController?.hide(
                    android.view.WindowInsets.Type.statusBars() or android.view.WindowInsets.Type.navigationBars()
                )
            } else {
                @Suppress("DEPRECATION")
                window.decorView.systemUiVisibility = (
                    View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                )
            }
        }
    }

    override fun onResume()  { super.onResume();  webView.onResume() }
    override fun onPause()   { super.onPause();   webView.onPause() }
    override fun onDestroy() {
        pingHandler.removeCallbacksAndMessages(null)
        webView.destroy()
        super.onDestroy()
    }
}

// ================================================================
// NativeBridge — JavaScript → Android native calls
// ================================================================
class NativeBridge(private val activity: MainActivity) {

    @JavascriptInterface
    fun vibrate(ms: Long) {
        val hapticEnabled = activity.getSharedPreferences(MainActivity.PREF_FILE, Context.MODE_PRIVATE)
            .getBoolean("haptic", false)
        if (!hapticEnabled) return
        val v = activity.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            v.vibrate(VibrationEffect.createOneShot(ms.coerceIn(10, 500), VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            v.vibrate(ms.coerceIn(10, 500))
        }
    }

    @JavascriptInterface
    fun getWifiSSID(): String {
        return try {
            val wm = activity.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            wm?.connectionInfo?.ssid?.trim('"') ?: "unknown"
        } catch (e: Exception) { "unknown" }
    }

    @JavascriptInterface
    fun setHost(host: String) {
        if (host.isBlank()) return
        activity.getSharedPreferences(MainActivity.PREF_FILE, Context.MODE_PRIVATE)
            .edit().putString(MainActivity.PREF_HOST, host.trim()).apply()
        activity.runOnUiThread { activity.recreate() }
    }

    @JavascriptInterface
    fun getHost(): String {
        return activity.getSharedPreferences(MainActivity.PREF_FILE, Context.MODE_PRIVATE)
            .getString(MainActivity.PREF_HOST, MainActivity.DEFAULT_HOST)
            ?: MainActivity.DEFAULT_HOST
    }

    @JavascriptInterface
    fun getApiBase(): String {
        val prefs = activity.getSharedPreferences(MainActivity.PREF_FILE, Context.MODE_PRIVATE)
        val host  = prefs.getString(MainActivity.PREF_HOST, MainActivity.DEFAULT_HOST) ?: MainActivity.DEFAULT_HOST
        val port  = prefs.getInt("port", MainActivity.DEFAULT_PORT)
        return "http://$host:$port"
    }

    @JavascriptInterface
    fun toast(msg: String) {
        activity.runOnUiThread { Toast.makeText(activity, msg, Toast.LENGTH_SHORT).show() }
    }

    @JavascriptInterface
    fun isNetworkAvailable(): Boolean {
        return try {
            val cm = activity.getSystemService(Context.CONNECTIVITY_SERVICE)
                as? android.net.ConnectivityManager ?: return false
            val caps = cm.getNetworkCapabilities(cm.activeNetwork ?: return false) ?: return false
            caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET)
        } catch (e: Exception) { false }
    }

    @JavascriptInterface
    fun getAppVersion(): String {
        return try {
            activity.packageManager.getPackageInfo(activity.packageName, 0).versionName ?: "1.0.0"
        } catch (e: Exception) { "1.0.0" }
    }
}
