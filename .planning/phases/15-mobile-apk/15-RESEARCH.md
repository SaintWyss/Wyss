# Phase 15: Mobile APK - Research

**Researched:** 2026-07-11
**Domain:** Capacitor 7 Android WebView shell over an existing local-first FastAPI bridge; TOFU TLS fingerprint pinning; QR-based pairing
**Confidence:** MEDIUM-HIGH overall — HIGH on bridge/cert code (read directly), HIGH on package registry existence (npm view + slopcheck), MEDIUM on the exact Capacitor-native pinning mechanism (no official Capacitor doc covers `onReceivedSslError`; pattern verified via GitHub issues/community sources, not Context7-first-party)

## Summary

Phase 15 wraps the existing SPA in a thin Capacitor 7 Android shell that is genuinely same-origin with the LAN bridge (`server.url`), and adds two things the web client doesn't need: (1) TOFU certificate-fingerprint pinning done in native Kotlin/Java code (because Android's `networkSecurityConfig` is static XML and Wyss's cert regenerates on IP change), and (2) a QR pairing flow that eliminates typing a 43-char token URL on a phone keyboard.

The hardest design problem is **not** cert pinning in isolation — it's the ordering: the app needs to render *something* before it knows the bridge's URL/fingerprint (which only exist after a QR scan), but Capacitor's `server.url` is a static, build-time config value. The verified resolution (confirmed via the official Capacitor Android custom-code docs plus community reports) is: ship the app with **no `server.url`** (bundled local assets, the Capacitor default) containing only a minimal pairing screen that does zero network calls to the bridge; a custom Capacitor plugin's native code performs the QR scan (via `@capacitor-mlkit/barcode-scanning`), stores the paired URL+fingerprint, and then calls `bridge.getWebView().loadUrl(pairedUrl)` from `MainActivity` — at that point the WebView navigates away from the bundled asset origin and becomes genuinely same-origin with the LAN bridge for the rest of the session. This sidesteps Pitfall 1 (bundled-local `https://localhost` colliding with the bridge's Origin allowlist) because the pairing screen never talks to the bridge — only the *post-navigation* WebView does, and by then it's same-origin, not cross-origin.

TLS trust is enforced by a custom `WebViewClient` (extending Capacitor's `BridgeWebViewClient`, installed via `bridge.setWebViewClient(...)` from a custom plugin per the official "Custom Native Android Code" doc) that overrides `onReceivedSslError`: extract the presented certificate's SHA-256 fingerprint and compare against the value captured at pairing time (same format `bootstrap/tls.py::fingerprint_sha256` already prints); `handler.proceed()` only on exact match, `handler.cancel()` + user-facing "re-pair" prompt otherwise. Extracting the raw certificate from Android's `SslError`/`SslCertificate` requires a documented-but-unofficial reflection trick (`SslCertificate.saveState()` → Bundle → `X509Certificate` bytes) that has been stable across Android API levels since it entered the public API surface, but is not part of the officially blessed `SslCertificate` public methods — flag this as the one piece of native code needing a device-verified checkpoint, not just a unit test.

**Primary recommendation:** Capacitor 7.6.7 (pinned, matches project's own prior decision to avoid the SDK-36 friction of v8), bundled-local pairing screen + native `loadUrl` handoff to `server.url`-equivalent runtime navigation, `@capacitor-mlkit/barcode-scanning@7.5.0` for QR decode, and a new `/pair` page in the existing authenticated SPA (using `qrcode-generator`, ~2.5kB, zero deps) for QR *generation* — smaller total surface than adding a Python QR-image dependency to the CLI.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| QR generation (encode url+fp+token) | Frontend Server (SSR-less SPA, client-side) | API/Backend (new `GET /api/pair` to supply fp+token) | Reuses the SPA's existing authenticated session; no new secret computation, just exposing already-computed values |
| QR decode / camera scan | Browser/Client (native Android, pre-pairing) | — | Happens entirely on-device before any network trust exists; must be native, not web (no bridge session yet) |
| TOFU fingerprint pinning | Browser/Client (native WebViewClient) | — | Android's WebView SSL trust decision is inherently a client-tier concern; the bridge/server has no visibility into what cert the phone accepted |
| Same-origin navigation handoff (`loadUrl`) | Browser/Client (native Activity/plugin) | — | Only native code can call `bridge.getWebView().loadUrl()`; this is the mechanism that turns a bundled-asset WebView into a same-origin one |
| Origin/Host/cookie auth | API/Backend (`bootstrap/web.py`) | — | Unchanged — the whole point of `server.url` same-origin design is that the phone becomes indistinguishable from the PC browser at this layer |
| Cert generation + fingerprint computation | API/Backend (`bootstrap/tls.py`) | — | Already exists; APK phase only *consumes* the fingerprint, never generates or validates server-side |
| CONFIRMAR gate (B/C proposals) | API/Backend (dispatch/policy engine) | Browser/Client (renders the gate UI) | No new logic — same SPA React components already used on desktop, served from the same origin |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@capacitor/core` | 7.6.7 `[VERIFIED: npm registry]` | Runtime bridge JS↔native | Pinned to 7.x per project's own prior research decision (avoids SDK 36 friction); confirmed latest 7.x tag via `npm view` |
| `@capacitor/cli` | 7.6.7 `[VERIFIED: npm registry]` | `npx cap init/add/sync/build` tooling | Official CLI, dev dependency only |
| `@capacitor/android` | 7.6.7 `[VERIFIED: npm registry]` | Native Android platform project (Gradle) | Official platform package; generates the `android/` project with bundled Gradle wrapper |
| `@capacitor-mlkit/barcode-scanning` | 7.5.0 `[VERIFIED: npm registry]` | QR decode on-device (ML Kit) | Peer dep `@capacitor/core >=7.0.0` — compatible with pinned 7.6.7; maintained community plugin (capawesome-team), avoids hand-rolling camera+decode pipeline |
| `qrcode-generator` | latest (pure JS, ~2.5kB minified, zero deps) `[VERIFIED: npm registry]` | QR **generation** (SVG/canvas) in the SPA's new `/pair` page | Smallest-surface option for encode-side; renders directly to SVG paths, no image/canvas dependency required |

### Supporting (native Android — no new package manager dependency, part of `android/` project once generated)
| Component | Purpose | When to Use |
|-----------|---------|-------------|
| Custom Kotlin/Java plugin class (hand-written, `android/app/src/main/java/...`) | Registers via `registerPlugin()` in `MainActivity`; owns pairing state (SharedPreferences) + installs the custom `WebViewClient` | Always — this is the load-bearing piece; no plugin exists off-the-shelf for "TOFU pin against a fingerprint captured from a QR payload" |
| `BridgeWebViewClient` subclass | Overrides `onReceivedSslError` for fingerprint comparison | Installed via `bridge.setWebViewClient(customClient)` inside the custom plugin's `load()`/constructor |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom native TOFU-pinning plugin | A general-purpose cert-pinning library (e.g. TrustKit-style static-pin libraries) | Those libraries assume pins are known at **build time** (baked-in SHA-256 of a known CA/leaf); Wyss's cert is generated per-machine at runtime and captured at pairing time — no existing library models "pin whatever the QR told you," so hand-rolling ~80 lines of Kotlin is less risk than fighting a library's static-pin assumption |
| Bundled-local pairing screen + native `loadUrl` handoff | Native Android Activity (no WebView at all) for the pairing screen, using CameraX + ML Kit directly (no Capacitor plugin) | Fully avoids any Capacitor/WebView ambiguity during pairing, but means writing two separate UI surfaces (native pairing screen + web app) instead of one Capacitor plugin; recommended fallback if the `@capacitor-mlkit` plugin's camera permission flow proves awkward inside a Capacitor bundled-asset WebView |
| `qrcode-generator` (JS, SPA `/pair` page) | Python `qrcode` (CLI ASCII output via `print_ascii()`, no Pillow needed) | Terminal ASCII QR codes are markedly less reliable to scan (compressed/rasterized in a text terminal, font-dependent) than an SVG rendered in a real browser viewport; the JS option also adds zero new Python dependencies to the CLI's audited surface |
| `@capacitor-mlkit/barcode-scanning` | Hand-rolled `getUserMedia` + `jsQR` in a bundled local HTML page | ML Kit is on-device, works without a network call, and doesn't require the WebView to hold the camera stream across a slow JS decode loop; the "hand-roll a JS decoder in the bundled pairing page" path is viable but re-derives what ML Kit already solves reliably |

**Installation:**
```bash
cd web
npm install @capacitor/core@7.6.7 @capacitor/android@7.6.7 @capacitor-mlkit/barcode-scanning@7.5.0 qrcode-generator
npm install -D @capacitor/cli@7.6.7
npx cap init "Wyss" "com.wyss.mobile" --web-dir=dist
npx cap add android
```

**Version verification:** `npm view @capacitor/core versions` confirms `7.6.7` is the latest 7.x release (8.4.1 is now the overall latest tag — do **not** `npm install @capacitor/core` unpinned, it will pull 8.x and break the SDK-35/no-Android-Studio environment assumption). `npm view @capacitor-mlkit/barcode-scanning@7.5.0 peerDependencies` returns `{"@capacitor/core": ">=7.0.0"}` — compatible.

## Package Legitimacy Audit

Ran `slopcheck install <pkgs> --ecosystem npm --force` from a scratch npm project (not the repo — an earlier run with `@version` suffixes falsely flagged 3 packages as `[SLOP]` due to a slopcheck registry-lookup quirk with scoped-package `@name@version` syntax; re-running with bare package names, no version suffix, resolved this and all 5 packages passed).

| Package | Registry | Age | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-------------|-----------|-------------|
| `@capacitor/core` | npm | mature (Capacitor project, years) | github.com/ionic-team/capacitor | OK | Approved |
| `@capacitor/cli` | npm | mature | github.com/ionic-team/capacitor | OK | Approved |
| `@capacitor/android` | npm | mature | github.com/ionic-team/capacitor | OK | Approved |
| `@capacitor-mlkit/barcode-scanning` | npm | maintained (capawesome-team) | github.com/capawesome-team/capacitor-mlkit | OK | Approved |
| `qrcode-generator` | npm | mature (kazuhikoarase, long-standing) | github.com/kazuhikoarase/qrcode-generator | OK | Approved |

**Packages removed due to slopcheck `[SLOP]` verdict:** none (the 3 earlier false-positives were a tool artifact of appending `@version` to scoped package names during the existence check — re-verified clean without the version suffix; version pinning is still applied at `npm install` time via the command above, just not during the slopcheck existence probe).
**Packages flagged as suspicious `[SUS]`:** none.

**IMPORTANT — side effect during research:** the first `slopcheck install` invocation was run with `cwd` inside the repo's `web/` directory and (because slopcheck defaults to installing whatever isn't blocked) executed `npm install`, modifying `web/package.json`/`web/package-lock.json` and `web/node_modules`. This was caught and reverted (`git checkout -- web/package.json web/package-lock.json` + removed the added `node_modules` entries) before this file was written. **The planner must run any future `slopcheck`/`npm install` invocations from a scratch directory or accept the install as an intentional task**, never as a side effect of a legitimacy check.

## Architecture Patterns

### System Architecture Diagram

```
┌─── FIRST LAUNCH (no pairing state) ─────────────────────────────────┐
│                                                                       │
│  Android app boots → Capacitor WebView loads BUNDLED local assets   │
│  (no server.url set → default androidScheme://localhost, offline)   │
│                          │                                           │
│                          ▼                                           │
│           Minimal pairing screen (camera permission + scan button)  │
│           — makes ZERO fetch/XHR calls to any bridge —                │
│                          │                                           │
│                          ▼                                           │
│   @capacitor-mlkit/barcode-scanning decodes QR → native plugin gets  │
│   JSON {v, url, fp, token}                                           │
│                          │                                           │
│                          ▼                                           │
│   Native plugin persists {url, fp} to SharedPreferences,             │
│   installs custom WebViewClient (TOFU check wired to `fp`),          │
│   then calls bridge.getWebView().loadUrl(url + "?token=" + token)    │
│                          │                                           │
│                          ▼                                           │
│   WebView navigates AWAY from bundled-asset origin → now genuinely   │
│   same-origin with https://<lan-ip>:7777 (Capacitor's own JS runtime │
│   keeps working because it was injected before navigation)           │
└───────────────────────────────────────────────────────────────────────┘

┌─── SUBSEQUENT LAUNCHES (pairing state exists) ──────────────────────┐
│  App boots → native code reads {url, fp} from SharedPreferences →   │
│  installs the fp-aware WebViewClient FIRST → calls loadUrl(url)     │
│  directly, skipping the pairing screen entirely →                    │
│  onReceivedSslError fires on TLS handshake → SHA-256(cert) == fp?   │
│    match    → handler.proceed() → normal same-origin SPA session     │
│    mismatch → handler.cancel() → native "cert changed, re-pair"      │
│               screen → user re-scans a fresh QR (APK-06)             │
└───────────────────────────────────────────────────────────────────────┘

┌─── DESKTOP SIDE (already-authenticated SPA session) ────────────────┐
│  Owner opens SPA on PC (already cookie-authenticated) → new /pair    │
│  route calls GET /api/pair (cookie-gated, same middleware as         │
│  everything else) → backend returns {url: lan_url, fp: fingerprint,  │
│  token: existing web_token} (all values it ALREADY computes at        │
│  `wyss web --lan --tls` startup — no new secret material) →          │
│  qrcode-generator renders an SVG QR client-side, nothing sent over    │
│  the network beyond the existing authenticated GET                   │
└───────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
web/
├── src/
│   └── pages/Pair.tsx          # new: renders QR from GET /api/pair (SVG via qrcode-generator)
├── capacitor.config.ts         # NO server.url set (bundled-local pairing default)
└── android/                    # generated by `npx cap add android`
    └── app/src/main/java/com/wyss/mobile/
        ├── MainActivity.java   # registers the custom plugin in onCreate()
        ├── PairingPlugin.java  # QR scan trigger, SharedPreferences, loadUrl() handoff
        └── PinnedWebViewClient.java  # extends BridgeWebViewClient, onReceivedSslError override
```

### Pattern 1: Runtime `server.url` via native `loadUrl`, not config
**What:** Capacitor's `server.url` is a static, compile-time config value intended for live-reload dev servers. To point the WebView at a URL only known at pairing time, do NOT set `server.url` — instead call `bridge.getWebView().loadUrl(dynamicUrl)` from native code after the URL is known.
**When to use:** Any Capacitor app whose backend URL isn't fixed at build time.
**Example:**
```java
// Source: community pattern (github.com/ionic-team/capacitor/issues/5110,
// forum.ionicframework.com/t/change-server-url-at-runtime/242068) — [ASSUMED],
// no official Capacitor doc covers this exact runtime-navigation use case.
public class PairingPlugin extends Plugin {
    @PluginMethod
    public void completePairing(PluginCall call) {
        String url = call.getString("url");
        String fingerprint = call.getString("fp");
        String token = call.getString("token");
        // persist fingerprint for PinnedWebViewClient to read
        getContext().getSharedPreferences("wyss_pairing", Context.MODE_PRIVATE)
            .edit()
            .putString("fp", fingerprint)
            .putString("url", url)
            .apply();
        getActivity().runOnUiThread(() ->
            getBridge().getWebView().loadUrl(url + "/?token=" + token)
        );
        call.resolve();
    }
}
```

### Pattern 2: TOFU fingerprint pinning via custom `WebViewClient`
**What:** Override `onReceivedSslError` on a `BridgeWebViewClient` subclass; extract the presented cert's SHA-256 and compare against the pinned value.
**When to use:** Any self-signed/dynamically-regenerated cert scenario where `networkSecurityConfig`'s static XML can't express the trust anchor.
**Example:**
```java
// Source: sslinsights.com pattern + AOSP SslCertificate source (the
// saveState()/X509Certificate extraction is a long-standing but NOT officially
// documented public-API workaround) — [ASSUMED], needs device verification.
public class PinnedWebViewClient extends BridgeWebViewClient {
    @Override
    public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
        String pinnedFp = prefs.getString("fp", null);
        if (pinnedFp == null) { handler.cancel(); return; }
        try {
            Bundle bundle = SslCertificate.saveState(error.getCertificate());
            byte[] bytes = bundle.getByteArray("x509-certificate");
            X509Certificate cert = (X509Certificate) CertificateFactory
                .getInstance("X.509")
                .generateCertificate(new ByteArrayInputStream(bytes));
            String presentedFp = sha256Fingerprint(cert.getEncoded()); // format: AA:BB:CC:...
            if (presentedFp.equalsIgnoreCase(pinnedFp)) {
                handler.proceed();
            } else {
                handler.cancel();
                notifyRepairNeeded(); // surface "cert changed, re-pair" to JS layer
            }
        } catch (Exception e) {
            handler.cancel(); // fail closed on any extraction error
        }
    }
}
```

### Pattern 3: QR payload schema
**What:** `{"v": 1, "url": "https://192.168.x.x:7777", "fp": "AA:BB:CC:...", "token": "<32-byte-urlsafe>"}`
**Rationale for including `token`:** The QR is rendered on a screen the owner already trusts by the existing threat model — today's pairing flow already puts the same token in a URL printed on the PC's own trusted terminal/browser session for the owner to copy to the phone (`cli.py`'s `phone_url` panel). A QR encoding the same value is not a security regression; it's the same trust boundary (physical visibility of the owner's own screen) with better UX (no 43-char manual entry). Do **not** treat this as equivalent to a QR posted publicly — the existing `SECURITY_MODEL.md` "Residual conocido: TOFU" already accepts this exposure model for the desktop flow.
**`v` field:** Allows future schema changes (e.g. adding a device-id) without breaking older paired apps mid-transition.

### Anti-Patterns to Avoid
- **Bundling the SPA as local assets AND letting it `fetch()` the bridge cross-origin:** This is Pitfall 1 from the project's own pitfalls research — the pairing screen must make zero network calls; only the post-`loadUrl` same-origin WebView talks to the bridge.
- **`onReceivedSslError` → unconditional `handler.proceed()`:** Never ship this, even temporarily — it is the single highest-severity anti-pattern in this phase (full MITM exposure). Treat any PR containing it as merge-blocking.
- **Setting `server.url` to a placeholder/dummy value "to satisfy the config schema":** Leave it unset; a dummy value risks accidentally being live-reload-reachable or confusing `allowNavigation` checks.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| QR image decode from camera frames | Custom `getUserMedia` + manual QR decode loop in JS | `@capacitor-mlkit/barcode-scanning` (native ML Kit) | On-device, reliable, maintained; a hand-rolled JS decoder in a bundled WebView fights camera-permission and performance issues ML Kit already solves |
| QR image generation | Server-side QR image rendering (PNG generation, extra endpoint complexity) | `qrcode-generator` client-side in the already-authenticated SPA | Zero new backend attack surface — the backend just returns 3 already-computed strings over the existing authenticated GET |
| JSON-RPC client / auth model on the phone | A separate mobile API client library | The existing bridge (`bootstrap/web.py`) — the WebView IS a normal same-origin browser session once `loadUrl` completes | This is the whole point of `server.url`/`loadUrl` same-origin design; building a separate mobile API client would duplicate Origin/cookie logic that's already correct |
| Full cert-pinning framework (TrustKit-style) | A general pinning library with static build-time pins | ~80 lines of hand-written `onReceivedSslError` comparison against a pairing-time fingerprint | No existing library models "pin whatever a QR just told you at runtime"; the custom code is small, testable in isolation, and matches the project's own TOFU model already documented in `SECURITY_MODEL.md` |

**Key insight:** Every "don't hand-roll" temptation in this phase is really about *not reinventing the bridge's existing same-origin auth model* — the only genuinely new native code is the pairing-time trust bootstrap (QR → fingerprint → pin), which by definition has no off-the-shelf solution because it depends on Wyss's own runtime-generated cert.

## Common Pitfalls

(Full detail on Pitfalls 1–3 already documented in `.planning/research/PITFALLS.md`; summarized here with APK-phase-specific additions.)

### Pitfall 1 (from PITFALLS.md): Bundled-asset `https://localhost` origin collision
**How to avoid (APK-specific):** The pairing screen must be verified to make **zero** `fetch`/`XMLHttpRequest` calls — add a build-time or code-review check (e.g. grep the pairing screen's JS bundle for `fetch(` / `XMLHttpRequest`) since a single stray network call during the bundled-asset phase reintroduces the collision.

### Pitfall 2 (from PITFALLS.md): `server.url` "not for production" + cleartext defaults
**APK-specific addition:** Since this phase deliberately does NOT use `server.url` at all (using `loadUrl` instead), the specific warning about `server.url`'s production-readiness doesn't directly apply — but `cleartext`/`usesCleartextTraffic` still matters if TLS (`wyss web --tls`) isn't always on. Since APK-04 requires the same origin as the LAN bridge and the bridge already supports `--tls`, **require `--tls` for the mobile flow specifically** (no cleartext fallback) — this also simplifies the pinning story to "always HTTPS, always check the cert."

### Pitfall 3 (from PITFALLS.md): Static `networkSecurityConfig` can't express a regenerating cert
Fully covered by Pattern 2 above (native TOFU pinning). Additional APK-phase nuance: **the `SslCertificate.saveState()` extraction trick is not part of Android's officially documented public API contract** for `SslCertificate` (it's a long-stable but undocumented Bundle key, `"x509-certificate"`) — this must be verified on a real device before being treated as reliable; if it ever breaks on a future Android version, the whole pinning mechanism silently fails, so wrap the extraction in a fail-closed try/catch (shown in Pattern 2) rather than assuming success.

### Pitfall 4 (new): Gradle-headless build without Android Studio
**What goes wrong:** `npx cap add android` generates a project expecting `local.properties` with `sdk.dir` pointing at the Android SDK, and Gradle needs `ANDROID_HOME`/`ANDROID_SDK_ROOT` set in the shell environment used for the build — neither is currently exported in this environment (`ANDROID_HOME` is empty per the environment probe), even though `~/Android/Sdk` exists with `build-tools/35.0.0` and `platforms/android-35` installed.
**How to avoid:** Export `ANDROID_HOME=$HOME/Android/Sdk` and `ANDROID_SDK_ROOT=$HOME/Android/Sdk` before running `npx cap sync android` / `./gradlew assembleDebug` (the generated `android/` project's Gradle wrapper (`gradlew`) is bundled — no system-wide `gradle` install is required, which matches the environment probe showing `gradle` not found but is not blocking). Also write `android/local.properties` with `sdk.dir=/home/saintwyss/Android/Sdk` as a belt-and-suspenders fallback since some Gradle plugin versions read that file preferentially over the env var.
**Warning signs:** `SDK location not found` Gradle error, or a build that silently downloads a *different* SDK/build-tools version than the one already installed (wasting time/disk) because Gradle couldn't find the existing one.

### Pitfall 5 (new): Debug-signed APK is fine for sideload, but don't ship the `handler.proceed()` fallback that debug builds tempt
**What goes wrong:** Android's default debug keystore signs `assembleDebug` output automatically — this is sufficient for personal sideload (APK-01..06 explicitly out-of-scope for Play Store), but debug builds commonly get a permissive `onReceivedSslError` "just to test" that then never gets removed before the owner starts relying on the app daily.
**How to avoid:** Keep the pinning logic identical between debug and any future release build variant — never gate `handler.proceed()` behind `BuildConfig.DEBUG`.

## Code Examples

### QR payload encode (SPA side, TypeScript)
```typescript
// Source: qrcode-generator README pattern (github.com/kazuhikoarase/qrcode-generator)
// — [CITED: github.com/kazuhikoarase/qrcode-generator]
import qrcode from "qrcode-generator";

function renderPairingQr(payload: { v: 1; url: string; fp: string; token: string }): string {
  const qr = qrcode(0, "M"); // type 0 = auto-detect size, ECC level M
  qr.addData(JSON.stringify(payload));
  qr.make();
  return qr.createSvgTag({ cellSize: 4, margin: 2 });
}
```

### New minimal backend endpoint (FastAPI, additive to `bootstrap/web.py`)
```python
# Reuses values bootstrap/web.py + bootstrap/tls.py already compute at startup;
# no new secret material, gated by the SAME cookie middleware as everything else.
@web_app.get("/api/pair")
async def api_pair() -> dict[str, str]:
    if lan_ip is None or not tls:
        raise WebError(
            status.HTTP_400_BAD_REQUEST,
            error="pairing requiere --lan --tls",
            accion="reiniciá con: wyss web --lan --tls",
        )
    return {
        "url": f"https://{lan_ip}:{port}",
        "fp": fingerprint_sha256(cert),  # already computed for the console panel
        "token": token,
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `androidScheme` defaulting to `file`/`http` | `https` by default since Capacitor 6 | Capacitor 6.0 (2024) | Directly caused Pitfall 1 (bundled-asset Origin now looks like a real HTTPS origin string, `https://localhost`) |
| Capacitor 8.x is the npm `latest` tag | Project deliberately pins 7.6.7 | Ongoing (8.x released after the project's SUMMARY.md research) | **Must explicitly pin the version in every install command** — an unpinned `npm install @capacitor/core` today would silently pull 8.4.1, contradicting the project's own SDK-35/no-Studio environment assumptions from SUMMARY.md |

**Deprecated/outdated:** None specific to this phase beyond the above version-pinning trap.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `bridge.getWebView().loadUrl(url)` from native code is the correct/only mechanism to navigate a Capacitor WebView to a runtime-determined URL, superseding a static `server.url` | Pattern 1 | If wrong, the entire pairing-handoff architecture needs a different mechanism (e.g. Capacitor's own internal navigation APIs, if any exist in 7.x that weren't surfaced by Context7/WebSearch) — MEDIUM risk, verify with a throwaway `npx cap add android` + minimal plugin spike before committing the full plan |
| A2 | `SslCertificate.saveState(cert)` → Bundle key `"x509-certificate"` reliably yields the DER-encoded cert bytes on Android API levels available on the owner's phone | Pattern 2, Pitfall 3 | HIGH risk if wrong — the entire TOFU pinning mechanism silently fails (either never proceeds, breaking APK-04, or the extraction throws and the fail-closed catch always cancels, meaning the app never connects). Must be device-verified before considering APK-03 done, not just unit-tested |
| A3 | Including the pairing `token` inside the QR payload is an acceptable security trade-off equivalent to the existing URL-with-token pairing flow | Pattern 3 | LOW-MEDIUM — if the owner's threat model has changed since `SECURITY_MODEL.md`'s "Residual conocido: TOFU" was written (e.g. QR is expected to be photographed/shared beyond the owner's own screen), this recommendation should be revisited; flag for owner confirmation during planning |
| A4 | A minimal bundled-local pairing screen making zero fetch calls avoids the Origin-allowlist collision entirely (no code change needed to `bootstrap/web.py`) | Architecture Patterns, Pitfall 1 | MEDIUM — if the ML Kit plugin or Capacitor's own JS runtime issues any background telemetry/fetch call during the bundled-asset phase, the collision could still occur; needs a network-log check during device testing |

**If this table is empty:** N/A — see entries above; all four should be confirmed with a device-level spike before the plan locks in the exact native code shape.

## Open Questions (RESOLVED — 2026-07-11)

1. **Does `@capacitor-mlkit/barcode-scanning`'s camera permission flow work smoothly from within a bundled-local (non-network) WebView context, or does it need to be a fully native Activity instead?**
   - What we know: The plugin is designed to work in any Capacitor WebView context per its own docs; peer-dep compatible with Capacitor 7.
   - What's unclear: Whether Android's runtime camera-permission dialog interacts cleanly with a WebView that has no `server.url` (some Capacitor plugins assume a live web server context for certain lifecycle callbacks).
   - Recommendation: Spike this first — `npx cap add android`, add the plugin, get a live QR scan working against a hardcoded fingerprint before writing the full pairing/pinning plugin. This is the single highest-value 30-minute verification before planning locks the task breakdown.

2. **Should the app persist pairing state across app reinstalls (i.e., should the fingerprint+URL survive `adb uninstall` + reinstall), or is re-pairing on every fresh install acceptable?** — RESOLVED: re-pairing tras reinstalación aceptado para v1.0
   - What we know: `SharedPreferences` data is wiped on uninstall by default (no Android Auto Backup configured for this data in the plan above).
   - What's unclared: Owner's UX expectation for reinstalls during development iteration (likely frequent, given sideload/no Play Store).
   - Recommendation: Accept re-pairing on reinstall for v1.0 (matches APK-06's "re-pairing is a normal, expected flow" framing) — do not add Android Auto Backup complexity for this.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | `npm install`, `npx cap` tooling | ✓ | v26.4.0 | — |
| npm | package install | ✓ | 12.0.0 | — |
| JDK | Gradle/Android build | ✓ | OpenJDK 21.0.11 | — |
| Android SDK (build-tools) | `assembleDebug` | ✓ | 35.0.0 (in `~/Android/Sdk/build-tools`) | — |
| Android SDK (platform) | `assembleDebug` | ✓ | android-35 (in `~/Android/Sdk/platforms`) | — |
| `ANDROID_HOME`/`ANDROID_SDK_ROOT` env var | Gradle SDK resolution | ✗ (currently unset in shell) | — | Export explicitly before build, or write `android/local.properties` with `sdk.dir=$HOME/Android/Sdk` |
| System `gradle` binary | — | ✗ | — | Not needed — `npx cap add android` generates a project with a bundled Gradle wrapper (`./gradlew`), which downloads its own Gradle distribution on first run |
| `slopcheck` | Package legitimacy audit | ✓ (installed during this research session via `pip install slopcheck --break-system-packages`) | 0.6.1 | — |

**Missing dependencies with no fallback:** None — the only "missing" item (`ANDROID_HOME`) has a direct, low-cost fallback (export the var / write `local.properties`).
**Missing dependencies with fallback:** `ANDROID_HOME` (see above), system `gradle` (bundled wrapper covers it).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework (Python/backend) | `pytest` (existing, per `web.py`/`tls.py` test conventions) |
| Framework (SPA/frontend) | `vitest` (existing, `web/package.json` already has `"test": "vitest run"`) |
| Framework (Android native) | JVM unit tests via Gradle (`./gradlew testDebugUnitTest`) — new for this phase, no existing Android test infra |
| Config file | `web/vitest.config.ts` (existing) / none yet for Android — Wave 0 gap |
| Quick run command | `cd web && npm run test` (frontend) / `pytest tests/test_bootstrap_web.py -x` (backend) |
| Full suite command | `pytest` (full backend) + `npm run test` (full frontend) + `./gradlew testDebugUnitTest` (Android, once scaffolded) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| APK-01 | APK installs and opens as a native app | manual-only | — (device install) | N/A — physical device checkpoint |
| APK-02 | QR encodes {v,url,fp,token}; app decodes it correctly | unit (both sides) | `npm run test -- Pair.test.tsx` (SPA encode) / `./gradlew testDebugUnitTest --tests PairingPayloadTest` (Android decode) | ❌ Wave 0 (both files new) |
| APK-03 | Fingerprint match/mismatch logic (pure function, no device needed) | unit (JVM, no Robolectric/device) | `./gradlew testDebugUnitTest --tests FingerprintMatcherTest` | ❌ Wave 0 |
| APK-03 (full E2E) | Real cert rotation is rejected until re-pair | manual-only | — (requires changing LAN IP or regenerating cert on a live device) | N/A — physical device checkpoint |
| APK-04 | `Origin: https://localhost` + LAN Host still 403s unless `null`+`Sec-Fetch-Site: same-origin` | integration | `pytest tests/test_bootstrap_web.py::test_origin_localhost_collision_still_rejected -x` | ❌ Wave 0 — regression test explicitly called for in PITFALLS.md, not yet written |
| APK-05 | CONFIRMAR gate renders/functions identically on phone-origin session | covered by existing SPA tests (same components, same origin) | `npm run test` (existing suite) | ✓ (no new test needed if truly same component tree) |
| APK-06 | Server down / IP changed → actionable error + re-pair path | manual-only (requires killing the daemon/bridge mid-session on a real device) | — | N/A — physical device checkpoint |
| `GET /api/pair` new endpoint | Returns {url,fp,token} only when `--lan --tls`, cookie-gated like everything else | integration | `pytest tests/test_bootstrap_web.py::test_api_pair_requires_tls_and_cookie -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** relevant quick command above (backend/frontend/Android, whichever changed)
- **Per wave merge:** full backend + frontend suites; Android unit tests once scaffolded
- **Phase gate:** Full suite green before `/gsd:verify-work`, PLUS the four manual-only device checkpoints (APK-01, APK-03 full E2E, APK-06) explicitly signed off by the owner on a physical phone — these cannot be automated in this environment

### Wave 0 Gaps
- [ ] `android/app/src/test/.../FingerprintMatcherTest.kt` — pure-function unit test for SHA-256 comparison logic (extract the comparison into a testable function separate from `onReceivedSslError` itself, which needs a real `SslError`/device)
- [ ] `android/app/src/test/.../PairingPayloadTest.kt` — decode `{v,url,fp,token}` JSON, reject malformed/missing-field payloads
- [ ] `web/src/pages/Pair.test.tsx` — encode payload → decodeable QR data round-trip (vitest, no camera/device needed)
- [ ] `tests/test_bootstrap_web.py::test_origin_localhost_collision_still_rejected` — the regression test PITFALLS.md explicitly calls for and that does not yet exist
- [ ] `tests/test_bootstrap_web.py::test_api_pair_requires_tls_and_cookie` — new endpoint's auth gating
- [ ] Android Gradle test framework install: none needed beyond what `npx cap add android` scaffolds (JUnit ships with the default Android Gradle template)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | Partial | Unchanged — same cookie/token model as desktop; APK adds no new authentication primitive, only a new *transport* (QR) for the existing token |
| V3 Session Management | Yes | Same `HttpOnly SameSite=Strict` cookie, 30-day max-age, already implemented in `bootstrap/web.py` — no change required |
| V4 Access Control | No new surface | Policy engine (`CognitivePolicyEngine`) untouched; phone proposes/confirms exactly like the desktop browser |
| V5 Input Validation | Yes | QR payload JSON must be schema-validated on decode (reject missing/malformed `v`/`url`/`fp`/`token` fields) before acting on it — treat QR content as untrusted input even though the *source* (owner's own screen) is trusted |
| V6 Cryptography | Yes | TOFU fingerprint pinning (SHA-256) — never weaken to a substring/prefix match; must be exact, case-insensitive hex comparison against the full 32-byte digest |
| V9 Communication Security | Yes | Mandate TLS (`--tls`) for the mobile flow specifically (no cleartext path) — simplifies the entire pinning story to "always verify a cert" |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| MITM via unconditional `onReceivedSslError.proceed()` | Tampering, Information Disclosure | Fail-closed fingerprint comparison (Pattern 2); merge-blocking review rule |
| Bundled-asset Origin collision with LAN allowlist | Spoofing | Zero-fetch pairing screen + same-origin `loadUrl` handoff (Architecture Patterns) |
| QR payload tampering/malformed injection into native code | Tampering | Schema-validate the decoded JSON before using any field; reject unknown `v` values |
| Stale/rotated cert silently accepted after IP change | Tampering (accepting wrong server) | Fail-closed on any fingerprint mismatch; explicit re-pair UX (APK-06), never a silent bypass |

## Sources

### Primary (HIGH confidence)
- `src/bootstrap/web.py`, `src/bootstrap/tls.py`, `src/bootstrap/cli.py` (read directly — Origin/Host/cookie middleware, cert generation/fingerprint format, existing `wyss web --lan --tls` panel/token flow)
- `.planning/research/SUMMARY.md`, `.planning/research/PITFALLS.md` (project's own prior research — Capacitor version decision, Pitfalls 1–3 fully documented there)
- `docs/mobile/WYSS_MOBILE_BRIDGE_MVP.md`, `docs/security/SECURITY_MODEL.md` (read directly — existing LAN bridge smoke test, TOFU threat model already accepted for desktop)
- [Capacitor Configuration docs (Context7 /ionic-team/capacitor-docs)](https://capacitorjs.com/docs/config) — `server.url` semantics, `CapacitorHttp`/`CapacitorCookies` plugin config
- [Capacitor Custom Native Android Code docs (Context7)](https://github.com/ionic-team/capacitor-docs/blob/main/docs/main/android/custom-code.md) — `registerPlugin()` pattern in `MainActivity`
- npm registry (`npm view`) — confirmed `@capacitor/core@7.6.7` is latest 7.x (8.4.1 is the overall `latest` tag), `@capacitor-mlkit/barcode-scanning@7.5.0` peer-dep-compatible
- `slopcheck 0.6.1` (installed and run in this session) — all 5 recommended packages `[OK]` on npm registry

### Secondary (MEDIUM confidence)
- [Custom WebViewClient / BridgeWebViewClient discussion (GitHub ionic-team/capacitor#3852, #5419, #2751)](https://github.com/ionic-team/capacitor/issues/3852) — `bridge.setWebViewClient()` pattern, confirms no first-party doc exists for this
- [Change server.url at runtime — Ionic Forum](https://forum.ionicframework.com/t/change-server-url-at-runtime/242068) — confirms `loadUrl()` from native `MainActivity` as the community-standard workaround
- [Android WebView self-signed certificate handling](https://sslinsights.com/how-to-handle-self-signed-certificates-in-android-webview/) — `onReceivedSslError` + `SslCertificate.saveState()` extraction pattern
- [qrcode-generator (kazuhikoarase)](https://github.com/kazuhikoarase/qrcode-generator) — pure-JS QR encode, SVG output API

### Tertiary (LOW confidence)
- None — all findings above were cross-checked against at least one official doc, direct code read, or a working `npm view`/`slopcheck` verification.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified via `npm view`, legitimacy verified via `slopcheck`, peer-dep compatibility checked directly
- Architecture: MEDIUM — the `loadUrl` handoff pattern and `onReceivedSslError`/`SslCertificate` extraction are community-verified, not first-party Capacitor/Android documented APIs; flagged in Assumptions Log for device-level spike before planning locks task shape
- Pitfalls: HIGH — Pitfalls 1–3 already validated against direct code reads in the project's own PITFALLS.md; new Pitfalls 4–5 (Gradle env, debug-build discipline) are straightforward environment/process facts

**Research date:** 2026-07-11
**Valid until:** 14 days (Capacitor major-version churn is fast — re-verify pinned version before executing if planning is delayed; the npm `latest` tag already moved to 8.x during this research)
