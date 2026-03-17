package com.r2d2.control

import android.annotation.SuppressLint
import android.content.Context
import android.net.wifi.WifiManager
import android.os.*
import android.view.*
import android.webkit.*
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.r2d2.control.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var webView: WebView

    companion object {
        const val PREF_FILE = "r2d2_prefs"
        const val PREF_HOST = "host"
        const val DEFAULT_HOST = "192.168.4.1"
        const val DEFAULT_PORT = 5000
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Full screen immersive — keep screen on during robot control
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
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

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        webView = binding.webview

        setupWebView()
        loadDashboard()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val prefs = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)

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
                    val host = prefs.getString(PREF_HOST, DEFAULT_HOST) ?: DEFAULT_HOST
                    view?.loadDataWithBaseURL(null, buildErrorHtml(host), "text/html", "UTF-8", null)
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
        val prefs = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        val host = prefs.getString(PREF_HOST, DEFAULT_HOST) ?: DEFAULT_HOST
        val port = prefs.getInt("port", DEFAULT_PORT)
        webView.loadUrl("http://$host:$port")
    }

    private fun buildErrorHtml(host: String): String = """
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <style>
            body { margin:0; background:#080c14; color:#8899aa; font-family:monospace;
                   display:flex; flex-direction:column; align-items:center;
                   justify-content:center; height:100vh; text-align:center; padding:20px; box-sizing:border-box; }
            h1   { color:#ff2244; font-size:28px; margin:0 0 8px; letter-spacing:3px; }
            h2   { color:#00aaff; font-size:16px; font-weight:normal; margin:0 0 32px; letter-spacing:2px; }
            .ip  { color:#00ffea; font-size:20px; background:rgba(0,170,255,0.1);
                   padding:10px 24px; border-radius:8px; border:1px solid rgba(0,170,255,0.3);
                   margin:16px 0; display:inline-block; }
            .step{ text-align:left; background:rgba(0,0,0,0.3); border-radius:12px;
                   padding:20px 28px; margin:16px 0; max-width:400px; line-height:2; }
            .step b { color:#00aaff; }
            button { margin-top:24px; padding:14px 32px; background:rgba(0,170,255,0.15);
                     border:1px solid #00aaff; border-radius:8px; color:#00aaff;
                     font-family:monospace; font-size:14px; letter-spacing:2px;
                     cursor:pointer; }
            button:active { background:rgba(0,170,255,0.3); }
            .pulse { animation: pulse 2s ease-in-out infinite; }
            @keyframes pulse { 0%,100%{opacity:.4} 50%{opacity:1} }
          </style>
        </head>
        <body>
          <h1>CONNECTION LOST</h1>
          <h2>R2-D2 CONTROL SYSTEM</h2>
          <div class="pulse" style="font-size:48px;">&#129302;</div>
          <div class="ip">http://$host:$DEFAULT_PORT</div>
          <div class="step">
            <b>1.</b> Verify R2-D2 is powered on<br>
            <b>2.</b> Connect your phone to WiFi <b>R2D2_Control</b><br>
            <b>3.</b> Press Retry
          </div>
          <button onclick="window.location.reload()">RETRY</button>
        </body>
        </html>
    """.trimIndent()

    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack()
        else super.onBackPressed()
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

    // Reload dashboard if we were showing an error page (network might be back)
    override fun onResume() {
        super.onResume()
        webView.onResume()
        if (webView.url?.startsWith("data:") == true) loadDashboard()
    }

    override fun onPause() {
        super.onPause()
        webView.onPause()
    }

    override fun onDestroy() {
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
                as? android.net.ConnectivityManager
            cm?.activeNetworkInfo?.isConnected ?: false
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
