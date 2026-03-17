package com.r2d2.control

import android.os.Bundle
import android.text.InputType
import androidx.appcompat.app.AppCompatActivity
import androidx.preference.*

class SettingsActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = getString(R.string.settings_title)
        supportFragmentManager.beginTransaction()
            .replace(R.id.settings_container, SettingsFragment())
            .commit()
    }

    override fun onSupportNavigateUp(): Boolean {
        onBackPressed()
        return true
    }
}

class SettingsFragment : PreferenceFragmentCompat() {
    override fun onCreatePreferences(savedInstanceState: Bundle?, rootKey: String?) {
        preferenceManager.sharedPreferencesName = MainActivity.PREF_FILE

        val screen = preferenceManager.createPreferenceScreen(requireContext())

        // ── Connection category ───────────────────────────────────
        val catConn = PreferenceCategory(requireContext()).apply {
            title = "R2-D2 Connection"
        }
        screen.addPreference(catConn)

        EditTextPreference(requireContext()).apply {
            key = MainActivity.PREF_HOST
            title = "Master IP Address"
            summary = "Default: 192.168.4.1 (R2-D2 hotspot)"
            setDefaultValue(MainActivity.DEFAULT_HOST)
            setOnBindEditTextListener { editText ->
                editText.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
                editText.hint = "192.168.4.1"
            }
            // Show current value in summary
            summaryProvider = EditTextPreference.SimpleSummaryProvider.getInstance()
            catConn.addPreference(this)
        }

        Preference(requireContext()).apply {
            title = "Port"
            summary = "5000 (fixed — matches Flask server)"
            isEnabled = false
            catConn.addPreference(this)
        }

        Preference(requireContext()).apply {
            title = "WiFi Network"
            summary = "Join R2D2_Control WiFi before connecting"
            isEnabled = false
            catConn.addPreference(this)
        }

        // ── Display category ──────────────────────────────────────
        val catDisplay = PreferenceCategory(requireContext()).apply {
            title = "Display"
        }
        screen.addPreference(catDisplay)

        SwitchPreferenceCompat(requireContext()).apply {
            key = "haptic"
            title = "Joystick haptic feedback"
            summary = "Light vibration when moving joystick"
            setDefaultValue(true)
            catDisplay.addPreference(this)
        }

        SwitchPreferenceCompat(requireContext()).apply {
            key = "keep_screen_on"
            title = "Keep screen on"
            summary = "Prevent screen from sleeping during control"
            setDefaultValue(true)
            catDisplay.addPreference(this)
        }

        // ── About category ────────────────────────────────────────
        val catAbout = PreferenceCategory(requireContext()).apply {
            title = "About"
        }
        screen.addPreference(catAbout)

        Preference(requireContext()).apply {
            title = "R2-D2 Control"
            summary = "Version 1.0.0 — WebView wrapper for R2-D2 dashboard"
            isEnabled = false
            catAbout.addPreference(this)
        }

        Preference(requireContext()).apply {
            title = "Dashboard URL"
            summary = "http://192.168.4.1:5000"
            isEnabled = false
            catAbout.addPreference(this)
        }

        preferenceScreen = screen
    }
}
