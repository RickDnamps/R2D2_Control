# R2-D2 Control — Android App

Native Android WebView wrapper for the R2-D2 dashboard.
Displays the Flask dashboard (`http://192.168.4.1:5000`) in a full-screen,
immersive WebView with haptic feedback on the virtual joystick.

---

## Prerequisites

| Tool | Version | Download |
|------|---------|----------|
| Android Studio | Hedgehog 2023.1+ | https://developer.android.com/studio |
| JDK | 17 (bundled with Android Studio) | — |
| Android SDK | API 34 (Android 14) | via SDK Manager in Android Studio |
| Kotlin | 1.9.0 (auto-downloaded by Gradle) | — |

> Android Studio includes its own JDK. You do not need to install JDK separately.

---

## 1. Open the Project in Android Studio

1. Launch Android Studio
2. Click **File → Open**
3. Navigate to `R2D2_Control/android/` and click **OK**
4. Wait for Gradle sync to complete (first sync downloads ~500 MB of dependencies)
5. If prompted to install missing SDK components, click **Install**

### SDK Manager (if needed)

Go to **Tools → SDK Manager** and install:
- Android SDK Platform 34
- Android SDK Build-Tools 34.0.0
- Android Emulator (optional — for testing without a physical device)

---

## 2. Build Debug APK

### From Android Studio

1. Select **Build → Build Bundle(s) / APK(s) → Build APK(s)**
2. APK location: `android/app/build/outputs/apk/debug/app-debug.apk`
3. Android Studio shows a notification with a direct link to the APK

### From command line (Linux/Mac)

```bash
cd android/
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

### From command line (Windows)

```cmd
cd android\
gradlew.bat assembleDebug
```

---

## 3. Install on Android Device

### Method A — USB Debugging (recommended for development)

1. On your Android phone, enable **Developer Options**:
   - Settings → About Phone → tap **Build number** 7 times
2. Enable **USB Debugging** in Developer Options
3. Connect phone via USB cable
4. In Android Studio: click the **Run** button (green triangle) or press **Shift+F10**
5. Select your device and click **OK**

### Method B — APK file transfer (no USB debugging needed)

1. Build the APK (see step 2 above)
2. Transfer `app-debug.apk` to your phone:
   - Via USB cable (copy to Downloads folder)
   - Via Google Drive / Dropbox
   - Via local web server: `python3 -m http.server 8080` then browse to your PC IP on phone
3. On your phone, open the APK file
4. If prompted about "Install unknown apps", enable it for your file manager
5. Tap **Install**

### Method C — ADB command line

```bash
adb install app/build/outputs/apk/debug/app-debug.apk
# Or update an existing install:
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

---

## 4. Connect to R2-D2

### Step 1 — Join the R2-D2 WiFi hotspot

On your Android phone:
- Settings → WiFi → Connect to **R2D2_Control**
- Default password: `r2d2droid`
- (Password configured during Master setup)

### Step 2 — Launch the app

- The app opens automatically at `http://192.168.4.1:5000`
- If R2-D2 is not powered on, an error screen is shown with a Retry button
- Once connected, the full dashboard appears in immersive full-screen mode

### Step 3 — Use the dashboard

- **Left joystick** — propulsion (throttle + steering)
- **Right joystick** — dome rotation
- **AUDIO tab** — play R2-D2 sounds by category
- **SYSTEMS tab** — Teeces LED control + servo panels
- **CONFIG tab** — WiFi settings + system reboot

---

## 5. Settings (IP configuration)

If R2-D2 uses a different IP (e.g., for testing with `preview.py` on your PC):

### Method A — In-app settings

The app exposes a `NativeBridge` JavaScript interface. From the dashboard's
browser console (or a custom button), call:

```javascript
// Change the Master IP
AndroidBridge.setHost("192.168.1.42");

// Check current IP
console.log(AndroidBridge.getHost());

// Check connected WiFi SSID
console.log(AndroidBridge.getWifiSSID());
```

### Method B — Build with custom IP

Edit `android/app/src/main/java/com/r2d2/control/MainActivity.kt`:

```kotlin
companion object {
    const val DEFAULT_HOST = "192.168.1.42"  // change here
    const val DEFAULT_PORT = 5000
}
```

Rebuild the APK.

---

## 6. Testing with preview.py (PC development)

`preview.py` is a mock Flask server at the repo root that simulates R2-D2 responses.

```bash
# On your PC
cd R2D2_Control/
python preview.py
# Server running at http://0.0.0.0:5000

# Find your PC's local IP
# Windows: ipconfig
# Mac/Linux: ip addr or ifconfig
```

Then in the Android app, set the host to your PC's local IP:

```javascript
AndroidBridge.setHost("192.168.1.X");  // replace X with your PC's last octet
```

Make sure your phone is on the same WiFi network as your PC.

---

## 7. PWA Alternative (no Android Studio needed)

The dashboard also works as a Progressive Web App (PWA) installable directly
from Chrome on Android:

1. Join the **R2D2_Control** WiFi
2. Open Chrome and navigate to `http://192.168.4.1:5000`
3. Tap the browser menu (three dots) → **Add to Home Screen**
4. Tap **Add**

The PWA installs to the home screen and runs in fullscreen landscape mode,
just like the native app. The service worker caches the UI for offline use.

**PWA vs Native App comparison:**

| Feature | PWA | Android App |
|---------|-----|-------------|
| Install | Chrome menu | APK file |
| Haptic joystick | No | Yes (AndroidBridge) |
| WiFi SSID check | No | Yes |
| Offline UI | Yes (service worker) | Yes (error page) |
| Full screen | Yes | Yes |
| Auto-landscape | Yes (manifest) | Yes |
| No Play Store needed | Yes | Yes |

---

## Architecture

```
android/
├── app/
│   ├── src/main/
│   │   ├── java/com/r2d2/control/
│   │   │   ├── MainActivity.kt      ← WebView setup, immersive mode
│   │   │   └── SettingsActivity.kt  ← IP config + preferences
│   │   ├── res/
│   │   │   ├── layout/
│   │   │   │   ├── activity_main.xml     ← WebView + loading overlay
│   │   │   │   └── activity_settings.xml ← Settings container
│   │   │   ├── values/
│   │   │   │   ├── strings.xml    ← App name
│   │   │   │   ├── colors.xml     ← R2-D2 dark theme colors
│   │   │   │   └── themes.xml     ← MaterialComponents dark theme
│   │   │   ├── drawable/
│   │   │   │   └── ic_r2d2.xml    ← R2-D2 vector icon
│   │   │   └── mipmap-*/
│   │   │       └── ic_launcher.xml ← Adaptive icon
│   │   └── AndroidManifest.xml
│   └── build.gradle
├── build.gradle
├── settings.gradle
├── gradle.properties
└── gradlew / gradlew.bat
```

## NativeBridge API

JavaScript functions available from the dashboard when running inside the Android app:

```javascript
// Check if running inside Android app
if (window.AndroidBridge) {
    // Haptic vibration (ms: 10-500)
    AndroidBridge.vibrate(20);

    // Get connected WiFi SSID
    const ssid = AndroidBridge.getWifiSSID();

    // Get/set Master IP
    const host = AndroidBridge.getHost();
    AndroidBridge.setHost("192.168.4.1");

    // Native Toast message
    AndroidBridge.toast("Hello from JS!");

    // Check network connectivity
    const connected = AndroidBridge.isNetworkAvailable();

    // App version
    const version = AndroidBridge.getAppVersion();
}
```

---

## Troubleshooting

**Gradle sync fails: "SDK location not found"**
- Open Android Studio SDK Manager → install Android SDK 34
- Or set `sdk.dir` in `android/local.properties`:
  ```
  sdk.dir=/Users/yourname/Library/Android/sdk
  ```

**Build fails: "Kotlin version mismatch"**
- File → Invalidate Caches / Restart → Invalidate and Restart

**App shows blank white screen**
- Verify phone is connected to **R2D2_Control** WiFi
- Verify R2-D2 Master is powered and Flask is running
- Check `usesCleartextTraffic="true"` in AndroidManifest.xml (already set)

**Haptic doesn't work**
- Enable vibration permission on the phone (Settings → Apps → R2-D2 Control → Permissions)
- Some phones require "vibrate" permission to be granted

**App exits fullscreen after notification**
- `onWindowFocusChanged` re-applies immersive mode automatically
