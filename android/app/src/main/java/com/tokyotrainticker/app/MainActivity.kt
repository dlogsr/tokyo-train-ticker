package com.tokyotrainticker.app

import android.annotation.SuppressLint
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.textfield.TextInputEditText

/**
 * Thin native wrapper around the existing 320x240 web frontend (frontend/index.html,
 * served by the FastAPI backend). Rather than reimplement the UI natively, this loads
 * the same page a browser would — the backend URL is the only thing configured here.
 * The home-screen widget (see widget/) is the native, at-a-glance piece of this app.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var settingsLayout: View
    private lateinit var backendUrlInput: TextInputEditText

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Targeting SDK 35+ forces edge-to-edge, so the toolbar would otherwise draw
        // underneath the status bar; pad the root by the system bar insets instead.
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.root)) { v, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }

        setSupportActionBar(findViewById<MaterialToolbar>(R.id.toolbar))

        webView = findViewById(R.id.webView)
        settingsLayout = findViewById(R.id.settingsLayout)
        backendUrlInput = findViewById(R.id.backendUrlInput)

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.webViewClient = WebViewClient()

        findViewById<View>(R.id.connectButton).setOnClickListener { connect() }

        val saved = Prefs.getBackendUrl(this)
        if (saved.isNotBlank()) {
            backendUrlInput.setText(saved)
            showWebView(saved)
        } else {
            backendUrlInput.setText(Prefs.DEFAULT_BACKEND_URL)
            showSettings()
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.visibility == View.VISIBLE && webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == R.id.action_settings) {
            showSettings()
            return true
        }
        return super.onOptionsItemSelected(item)
    }

    private fun connect() {
        val raw = backendUrlInput.text?.toString().orEmpty()
        if (raw.isBlank()) {
            Toast.makeText(this, R.string.settings_error_empty, Toast.LENGTH_SHORT).show()
            return
        }
        val url = BackendClient.normalizeBaseUrl(raw)
        Prefs.setBackendUrl(this, url)
        showWebView(url)
    }

    private fun showSettings() {
        settingsLayout.visibility = View.VISIBLE
        webView.visibility = View.GONE
    }

    private fun showWebView(baseUrl: String) {
        settingsLayout.visibility = View.GONE
        webView.visibility = View.VISIBLE
        webView.loadUrl(baseUrl)
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }
}
