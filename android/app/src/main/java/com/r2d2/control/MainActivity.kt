package com.r2d2.control

import android.annotation.SuppressLint
import android.content.Context
import android.net.wifi.WifiManager
import android.os.*
import android.view.*
import android.webkit.*
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
        const val PREF_FILE = "r2d2_prefs"
        const val PREF_HOST = "host"
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

        // Full screen immersive — must be after setContentView (DecorView required)
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
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            mediaPlaybackRequiresUserGesture = false
            cacheMode = WebSettings.LOAD_DEFAULT
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            allowUniversalAccessFromFileURLs = true
            allowFileAccessFromFileURLs = true
        }

        // Native bridge: vibration, WiFi info, settings
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
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                return false // Handle all navigation inside the WebView
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(msg: ConsoleMessage?): Boolean {
                return true // Suppress console output
            }
        }
    }

    private fun loadDashboard() {
        webView.loadUrl("file:///android_asset/index.html")
        startPingLoop()
    }

    private fun startPingLoop() {
        val prefs = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        val host = prefs.getString(PREF_HOST, DEFAULT_HOST) ?: DEFAULT_HOST
        val port = prefs.getInt("port", DEFAULT_PORT)
        pingHandler.post(object : Runnable {
            override fun run() {
                Thread {
                    val online = checkServer(host, port)
                    runOnUiThread {
                        if (online != isServerOnline) {
                            isServerOnline = online
                            updateStatusBanner(host, port, online)
                            // Reload WebView when server comes back online
                            if (online) webView.evaluateJavascript(
                                "window.R2D2_API_BASE = 'http://$host:$port'; if(typeof pollStatus==='function') pollStatus();", null
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
            val url = URL("http://$host:$port/status")
            val conn = url.openConnection() as HttpURLConnection
            conn.connectTimeout = 3000
            conn.readTimeout = 3000
            conn.requestMethod = "GET"
            val code = conn.responseCode
            conn.disconnect()
            code in 200..299
        } catch (e: Exception) {
            false
        }
    }

    private fun updateStatusBanner(host: String, port: Int, online: Boolean) {
        binding.statusHost.text = "$host:$port"
        if (online) {
            binding.statusDot.setTextColor(android.graphics.Color.parseColor("#00ff88"))
            binding.statusText.text = "EN LIGNE"
            binding.statusText.setTextColor(android.graphics.Color.parseColor("#00ff88"))
            binding.statusBanner.setBackgroundColor(android.graphics.Color.parseColor("#00100a"))
        } else {
            binding.statusDot.setTextColor(android.graphics.Color.parseColor("#ff2244"))
            binding.statusText.text = "HORS LIGNE"
            binding.statusText.setTextColor(android.graphics.Color.parseColor("#ff2244"))
            binding.statusBanner.setBackgroundColor(android.graphics.Color.parseColor("#0d0014"))
        }
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

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onPause() {
        super.onPause()
        webView.onPause()
    }

    override fun onDestroy() {
        pingHandler.removeCallbacksAndMessages(null)
        webView.destroy()
        super.onDestroy()
    }
}

// ================================================================
// NativeBridge — JavaScript to Android native calls
// ================================================================
class NativeBridge(private val activity: MainActivity) {

    /**
     * Haptic vibration for joystick feedback.
     * Called from JavaScript: AndroidBridge.vibrate(20)
     * @param ms Duration in milliseconds (clamped 10–500ms)
     */
    @JavascriptInterface
    fun vibrate(ms: Long) {
        val hapticEnabled = activity.getSharedPreferences(MainActivity.PREF_FILE, Context.MODE_PRIVATE)
            .getBoolean("haptic", false)
        if (!hapticEnabled) return
        val v = activity.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            v.vibrate(
                VibrationEffect.createOneShot(
                    ms.coerceIn(10, 500),
                    VibrationEffect.DEFAULT_AMPLITUDE
                )
            )
        } else {
            @Suppress("DEPRECATION")
            v.vibrate(ms.coerceIn(10, 500))
        }
    }

    /**
     * Returns the SSID of the currently connected WiFi network.
     * Useful to verify the phone is on R2D2_Control hotspot.
     * Called from JavaScript: AndroidBridge.getWifiSSID()
     */
    @JavascriptInterface
    fun getWifiSSID(): String {
        return try {
            val wm = activity.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            wm?.connectionInfo?.ssid?.trim('"') ?: "unknown"
        } catch (e: Exception) {
            "unknown"
        }
    }

    /**
     * Update the Master IP address and restart the app to reconnect.
     * Saved in SharedPreferences.
     * Called from JavaScript: AndroidBridge.setHost("192.168.4.1")
     */
    @JavascriptInterface
    fun setHost(host: String) {
        if (host.isBlank()) return
        activity.getSharedPreferences(MainActivity.PREF_FILE, Context.MODE_PRIVATE)
            .edit()
            .putString(MainActivity.PREF_HOST, host.trim())
            .apply()
        activity.runOnUiThread { activity.recreate() }
    }

    /**
     * Returns the configured Master IP address.
     * Called from JavaScript: AndroidBridge.getHost()
     */
    @JavascriptInterface
    fun getHost(): String {
        return activity.getSharedPreferences(MainActivity.PREF_FILE, Context.MODE_PRIVATE)
            .getString(MainActivity.PREF_HOST, MainActivity.DEFAULT_HOST)
            ?: MainActivity.DEFAULT_HOST
    }

    /**
     * Returns the full API base URL (http://host:port).
     * Called from JavaScript: AndroidBridge.getApiBase()
     */
    @JavascriptInterface
    fun getApiBase(): String {
        val prefs = activity.getSharedPreferences(MainActivity.PREF_FILE, Context.MODE_PRIVATE)
        val host = prefs.getString(MainActivity.PREF_HOST, MainActivity.DEFAULT_HOST) ?: MainActivity.DEFAULT_HOST
        val port = prefs.getInt("port", MainActivity.DEFAULT_PORT)
        return "http://$host:$port"
    }

    /**
     * Show a native Android Toast message.
     * Called from JavaScript: AndroidBridge.toast("Message")
     */
    @JavascriptInterface
    fun toast(msg: String) {
        activity.runOnUiThread {
            Toast.makeText(activity, msg, Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * Check if the device is connected to any network.
     * Called from JavaScript: AndroidBridge.isNetworkAvailable()
     */
    @JavascriptInterface
    fun isNetworkAvailable(): Boolean {
        return try {
            val cm = activity.getSystemService(Context.CONNECTIVITY_SERVICE)
                as? android.net.ConnectivityManager ?: return false
            val network = cm.activeNetwork ?: return false
            val caps = cm.getNetworkCapabilities(network) ?: return false
            caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET)
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Returns app version string.
     * Called from JavaScript: AndroidBridge.getAppVersion()
     */
    @JavascriptInterface
    fun getAppVersion(): String {
        return try {
            val pi = activity.packageManager.getPackageInfo(activity.packageName, 0)
            pi.versionName ?: "1.0.0"
        } catch (e: Exception) {
            "1.0.0"
        }
    }
}
