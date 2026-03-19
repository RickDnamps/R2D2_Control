package com.r2d2.control

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.Context
import android.net.wifi.WifiManager
import android.os.*
import android.text.InputType
import android.view.*
import android.webkit.*
import android.widget.*
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import com.r2d2.control.databinding.ActivityMainBinding
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var webView: WebView
    private var isServerOnline    = false
    private var pingFailureCount  = 0
    private var autoDiscovering   = false
    private val pingHandler       = Handler(Looper.getMainLooper())

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
                View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            )
        }

        binding.statusHost.setOnClickListener { showHostDialog() }

        setupWebView()
        loadDashboard()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack()
                else { isEnabled = false; onBackPressedDispatcher.onBackPressed() }
            }
        })
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView.settings.apply {
            javaScriptEnabled                = true
            domStorageEnabled                = true
            loadWithOverviewMode             = true
            useWideViewPort                  = true
            setSupportZoom(false)
            builtInZoomControls              = false
            displayZoomControls              = false
            mediaPlaybackRequiresUserGesture = false
            cacheMode                        = WebSettings.LOAD_DEFAULT
            mixedContentMode                 = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            allowUniversalAccessFromFileURLs = true
            allowFileAccessFromFileURLs      = true
        }
        webView.addJavascriptInterface(NativeBridge(this), "AndroidBridge")
        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(v: WebView?, u: String?, f: android.graphics.Bitmap?) {
                binding.loadingOverlay.visibility = View.VISIBLE
            }
            override fun onPageFinished(v: WebView?, u: String?) {
                binding.loadingOverlay.visibility = View.GONE
                // Injecter l'URL du Master avant que init() tourne
                val prefs = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
                val host  = prefs.getString(PREF_HOST, DEFAULT_HOST) ?: DEFAULT_HOST
                val port  = prefs.getInt("port", DEFAULT_PORT)
                v?.evaluateJavascript("window.R2D2_API_BASE='http://$host:$port';", null)
            }
            override fun onReceivedError(v: WebView?, r: WebResourceRequest?, e: WebResourceError?) {
                if (r?.isForMainFrame == true) binding.loadingOverlay.visibility = View.GONE
            }
            override fun shouldOverrideUrlLoading(v: WebView?, r: WebResourceRequest?) = false
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(m: ConsoleMessage?) = true
        }
    }

    private fun loadDashboard() {
        webView.loadUrl("file:///android_asset/index.html")
        startPingLoop()
    }

    // ================================================================
    // Ping loop + auto-discovery
    // ================================================================

    private fun startPingLoop() {
        pingHandler.removeCallbacksAndMessages(null)
        val prefs = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        val host  = prefs.getString(PREF_HOST, DEFAULT_HOST) ?: DEFAULT_HOST
        val port  = prefs.getInt("port", DEFAULT_PORT)
        binding.statusHost.text = "$host:$port"

        pingHandler.post(object : Runnable {
            override fun run() {
                Thread {
                    val online = checkServer(host, port)
                    runOnUiThread {
                        if (online) {
                            pingFailureCount = 0
                            autoDiscovering  = false
                            if (!isServerOnline) {
                                isServerOnline = true
                                updateStatusBanner(host, port, true)
                                webView.evaluateJavascript(
                                    "window.R2D2_API_BASE='http://$host:$port';" +
                                    "if(typeof pollStatus==='function') pollStatus();", null
                                )
                            }
                        } else {
                            pingFailureCount++
                            if (isServerOnline) {
                                isServerOnline = false
                                updateStatusBanner(host, port, false)
                            }
                            // Auto-discover after 3 consecutive failures (once per session)
                            if (pingFailureCount == 3 && !autoDiscovering) {
                                autoDiscovering = true
                                startAutoDiscover()
                            }
                        }
                    }
                    pingHandler.postDelayed(this, if (online) 15_000L else 5_000L)
                }.start()
            }
        })
    }

    /** Lance l'auto-découverte en arrière-plan. Met à jour le banner pendant la recherche. */
    private fun startAutoDiscover() {
        binding.statusText.text = "RECHERCHE R2-D2..."
        Thread {
            val found = tryDiscover()
            runOnUiThread {
                if (found != null) {
                    getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
                        .edit().putString(PREF_HOST, found).apply()
                    Toast.makeText(this, "R2-D2 trouvé : $found", Toast.LENGTH_SHORT).show()
                    isServerOnline   = false
                    autoDiscovering  = false
                    pingFailureCount = 0
                    startPingLoop()
                } else {
                    autoDiscovering = false
                    binding.statusText.text = "HORS LIGNE"
                }
            }
        }.start()
    }

    // ================================================================
    // Découverte réseau
    // ================================================================

    /** Tente de trouver le Master R2-D2 dans l'ordre : mDNS → IP sauvegardée → hotspot → scan subnet. */
    private fun tryDiscover(): String? {
        // 1. mDNS : r2-master.local (fonctionne sur hotspot et WiFi maison si avahi actif)
        try {
            val addr = InetAddress.getByName("r2-master.local")
            val ip   = addr.hostAddress ?: ""
            if (ip.isNotEmpty() && !addr.isLoopbackAddress && checkServer(ip, DEFAULT_PORT))
                return ip
        } catch (_: Exception) {}

        // 2. IP sauvegardée (déjà testée dans le ping — ici on re-essaie avec un peu de délai)
        val prefs       = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        val savedHost   = prefs.getString(PREF_HOST, "") ?: ""
        if (savedHost.isNotEmpty() && checkServer(savedHost, DEFAULT_PORT)) return savedHost

        // 3. IP hotspot par défaut
        if (checkServer("192.168.4.1", DEFAULT_PORT)) return "192.168.4.1"

        // 4. Scan subnet courant (WiFi)
        val subnet = getWifiSubnet() ?: return null
        if (subnet == "192.168.4") return null // déjà testé ci-dessus
        return scanSubnet(subnet)
    }

    /** Retourne le préfixe subnet courant ex: "192.168.2" ou null. */
    @Suppress("DEPRECATION")
    private fun getWifiSubnet(): String? {
        return try {
            val wm   = applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return null
            val ip   = wm.dhcpInfo?.ipAddress ?: return null
            val a    = ip         and 0xff
            val b    = ip shr 8   and 0xff
            val c    = ip shr 16  and 0xff
            if (a == 0 && b == 0 && c == 0) null else "$a.$b.$c"
        } catch (_: Exception) { null }
    }

    /** Scan les 254 IPs du subnet en parallèle (50 threads, timeout 500ms). ~3s max. */
    private fun scanSubnet(subnet: String): String? {
        val result = AtomicReference<String>(null)
        val latch  = CountDownLatch(254)
        val pool   = Executors.newFixedThreadPool(50)
        for (i in 1..254) {
            pool.submit {
                try {
                    val ip = "$subnet.$i"
                    if (result.get() == null && checkServerFast(ip, DEFAULT_PORT))
                        result.compareAndSet(null, ip)
                } finally { latch.countDown() }
            }
        }
        latch.await(8, TimeUnit.SECONDS)
        pool.shutdownNow()
        return result.get()
    }

    // ================================================================
    // Connexion HTTP
    // ================================================================

    private fun checkServer(host: String, port: Int): Boolean = httpGet(host, port, 3000)
    private fun checkServerFast(host: String, port: Int): Boolean = httpGet(host, port, 500)

    private fun httpGet(host: String, port: Int, timeoutMs: Int): Boolean {
        if (host.isBlank()) return false
        return try {
            val conn = URL("http://$host:$port/status").openConnection() as HttpURLConnection
            conn.connectTimeout = timeoutMs
            conn.readTimeout    = timeoutMs
            conn.requestMethod  = "GET"
            val code = conn.responseCode
            conn.disconnect()
            code in 200..299
        } catch (_: Exception) { false }
    }

    // ================================================================
    // UI — Banner + Dialog
    // ================================================================

    private fun updateStatusBanner(host: String, port: Int, online: Boolean) {
        binding.statusHost.text = "$host:$port"
        if (online) {
            val h = binding.statusBanner.height.takeIf { it > 0 }
                ?: (37 * resources.displayMetrics.density).toInt()
            binding.statusBanner.animate()
                .translationY(-h.toFloat())
                .setDuration(350)
                .withEndAction { binding.statusBanner.visibility = View.GONE }
                .start()
        } else {
            binding.statusBanner.visibility = View.VISIBLE
            binding.statusBanner.animate().translationY(0f).setDuration(350).start()
            binding.statusDot.setTextColor(android.graphics.Color.parseColor("#ff2244"))
            binding.statusText.text = "HORS LIGNE"
            binding.statusText.setTextColor(android.graphics.Color.parseColor("#ff2244"))
            binding.statusHost.setTextColor(android.graphics.Color.parseColor("#00aaff"))
        }
    }

    /** Dialog : champ IP + bouton RECHERCHER qui scanne le réseau. */
    private fun showHostDialog() {
        val prefs       = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        val currentHost = prefs.getString(PREF_HOST, DEFAULT_HOST) ?: DEFAULT_HOST
        val dp          = resources.displayMetrics.density

        // Build custom view
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val padH = (20 * dp).toInt(); val padV = (12 * dp).toInt()
            setPadding(padH, padV, padH, 0)
        }

        val statusLabel = TextView(this).apply {
            text       = "Essayez r2-master.local (mDNS) ou scannez le réseau."
            textSize   = 11f
            setTextColor(android.graphics.Color.parseColor("#8899aa"))
            visibility = View.VISIBLE
        }

        val progressBar = ProgressBar(this, null, android.R.attr.progressBarStyleSmall).apply {
            visibility        = View.GONE
            indeterminateTintList = android.content.res.ColorStateList.valueOf(
                android.graphics.Color.parseColor("#00aaff")
            )
        }

        val ipRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity     = Gravity.CENTER_VERTICAL
            setPadding(0, (8 * dp).toInt(), 0, 0)
        }

        val ipInput = EditText(this).apply {
            setText(currentHost)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setTextColor(android.graphics.Color.WHITE)
            setHintTextColor(android.graphics.Color.parseColor("#556677"))
            hint = "192.168.4.1"
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            setSelection(text.length)
        }

        val scanBtn = Button(this).apply {
            text      = "RECHERCHER"
            textSize  = 10f
            setTextColor(android.graphics.Color.parseColor("#00aaff"))
            setBackgroundColor(android.graphics.Color.TRANSPARENT)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { marginStart = (8 * dp).toInt() }
        }

        ipRow.addView(ipInput)
        ipRow.addView(scanBtn)

        container.addView(statusLabel)
        container.addView(progressBar)
        container.addView(ipRow)

        val dialog = AlertDialog.Builder(this)
            .setTitle("Adresse IP du Master R2-D2")
            .setView(container)
            .setPositiveButton("CONNECTER") { _, _ ->
                applyNewHost(ipInput.text.toString().trim())
            }
            .setNegativeButton("ANNULER", null)
            .create()

        scanBtn.setOnClickListener {
            scanBtn.isEnabled    = false
            progressBar.visibility = View.VISIBLE
            statusLabel.text     = "Recherche en cours…"
            statusLabel.setTextColor(android.graphics.Color.parseColor("#00aaff"))

            Thread {
                val found = tryDiscover()
                runOnUiThread {
                    progressBar.visibility = View.GONE
                    scanBtn.isEnabled      = true
                    if (found != null) {
                        ipInput.setText(found)
                        ipInput.setSelection(found.length)
                        statusLabel.text = "✓ R2-D2 trouvé : $found"
                        statusLabel.setTextColor(android.graphics.Color.parseColor("#00cc66"))
                    } else {
                        statusLabel.text = "Aucun R2-D2 trouvé sur le réseau."
                        statusLabel.setTextColor(android.graphics.Color.parseColor("#ff2244"))
                    }
                }
            }.start()
        }

        dialog.show()
    }

    private fun applyNewHost(newHost: String) {
        if (newHost.isBlank()) return
        getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
            .edit().putString(PREF_HOST, newHost).apply()
        isServerOnline   = false
        autoDiscovering  = false
        pingFailureCount = 0
        binding.statusBanner.clearAnimation()
        binding.statusBanner.translationY = 0f
        binding.statusBanner.visibility   = View.VISIBLE
        binding.statusDot.setTextColor(android.graphics.Color.parseColor("#ff2244"))
        binding.statusText.text = "HORS LIGNE"
        binding.statusText.setTextColor(android.graphics.Color.parseColor("#ff2244"))
        webView.evaluateJavascript("window.R2D2_API_BASE='http://$newHost:$DEFAULT_PORT';", null)
        startPingLoop()
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
        // Écran éteint ou app en arrière-plan → WebView figé → plus de HBs JS
        // Envoyer un stop natif pour ne pas laisser le robot en mouvement
        val prefs = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        val host  = prefs.getString(PREF_HOST, DEFAULT_HOST) ?: DEFAULT_HOST
        Thread {
            try {
                val url = URL("http://$host:$DEFAULT_PORT/motion/stop")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod  = "POST"
                conn.connectTimeout = 1000
                conn.readTimeout    = 1000
                conn.doOutput       = true
                conn.outputStream.close()
                conn.responseCode   // force send
                conn.disconnect()
            } catch (_: Exception) {}
        }.start()
    }
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
            @Suppress("DEPRECATION")
            wm?.connectionInfo?.ssid?.trim('"') ?: "unknown"
        } catch (_: Exception) { "unknown" }
    }

    @JavascriptInterface
    fun setHost(host: String) {
        if (host.isBlank()) return
        activity.getSharedPreferences(MainActivity.PREF_FILE, Context.MODE_PRIVATE)
            .edit().putString(MainActivity.PREF_HOST, host.trim()).apply()
        activity.runOnUiThread { activity.recreate() }
    }

    @JavascriptInterface
    fun getHost(): String =
        activity.getSharedPreferences(MainActivity.PREF_FILE, Context.MODE_PRIVATE)
            .getString(MainActivity.PREF_HOST, MainActivity.DEFAULT_HOST) ?: MainActivity.DEFAULT_HOST

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
            val cm   = activity.getSystemService(Context.CONNECTIVITY_SERVICE) as? android.net.ConnectivityManager ?: return false
            val caps = cm.getNetworkCapabilities(cm.activeNetwork ?: return false) ?: return false
            caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET)
        } catch (_: Exception) { false }
    }

    @JavascriptInterface
    fun getAppVersion(): String {
        return try {
            activity.packageManager.getPackageInfo(activity.packageName, 0).versionName ?: "1.0.0"
        } catch (_: Exception) { "1.0.0" }
    }
}
