package com.tokyotrainticker.app.widget

import android.app.Activity
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Spinner
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.textfield.TextInputEditText
import com.tokyotrainticker.app.BackendClient
import com.tokyotrainticker.app.Prefs
import com.tokyotrainticker.app.R
import com.tokyotrainticker.app.Station
import java.util.concurrent.Executors

/**
 * Launched by the system when a widget instance is placed (and re-launchable later
 * by tapping an unconfigured widget). Picks the backend URL + station this widget
 * instance tracks, saves it to Prefs, and asks TrainWidgetProvider to refresh right away.
 */
class TrainWidgetConfigureActivity : AppCompatActivity() {

    private val executor = Executors.newSingleThreadExecutor()
    private var appWidgetId = AppWidgetManager.INVALID_APPWIDGET_ID
    private var stations: List<Station> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setResult(Activity.RESULT_CANCELED)
        setContentView(R.layout.activity_widget_configure)

        appWidgetId = intent?.extras?.getInt(
            AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID
        ) ?: AppWidgetManager.INVALID_APPWIDGET_ID
        if (appWidgetId == AppWidgetManager.INVALID_APPWIDGET_ID) {
            finish()
            return
        }

        val backendUrlInput = findViewById<TextInputEditText>(R.id.backendUrlInput)
        val loadStationsButton = findViewById<View>(R.id.loadStationsButton)
        val loadingIndicator = findViewById<View>(R.id.loadingIndicator)
        val statusText = findViewById<android.widget.TextView>(R.id.statusText)
        val stationSpinner = findViewById<Spinner>(R.id.stationSpinner)
        val saveButton = findViewById<View>(R.id.saveButton)

        val existingUrl = Prefs.getBackendUrl(this)
        backendUrlInput.setText(existingUrl.ifBlank { Prefs.DEFAULT_BACKEND_URL })

        loadStationsButton.setOnClickListener {
            val raw = backendUrlInput.text?.toString().orEmpty()
            if (raw.isBlank()) {
                Toast.makeText(this, R.string.settings_error_empty, Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            val url = BackendClient.normalizeBaseUrl(raw)
            loadingIndicator.visibility = View.VISIBLE
            statusText.text = getString(R.string.widget_loading)
            stationSpinner.visibility = View.GONE
            saveButton.visibility = View.GONE

            executor.execute {
                val result = runCatching { BackendClient.fetchStations(url) }.getOrDefault(emptyList())
                runOnUiThread {
                    loadingIndicator.visibility = View.GONE
                    if (result.isEmpty()) {
                        statusText.text = getString(R.string.widget_load_failed)
                        return@runOnUiThread
                    }
                    stations = result
                    statusText.text = ""
                    stationSpinner.adapter = ArrayAdapter(
                        this,
                        android.R.layout.simple_spinner_dropdown_item,
                        result.map { "${it.nameEn} (${it.nameJa})" },
                    )
                    stationSpinner.visibility = View.VISIBLE
                    saveButton.visibility = View.VISIBLE
                    Prefs.setBackendUrl(this, url)
                }
            }
        }

        saveButton.setOnClickListener {
            val selected = stations.getOrNull(stationSpinner.selectedItemPosition) ?: return@setOnClickListener
            Prefs.setWidgetStation(this, appWidgetId, selected.id, selected.nameEn)
            requestImmediateRefresh()

            val resultValue = Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
            setResult(Activity.RESULT_OK, resultValue)
            finish()
        }
    }

    private fun requestImmediateRefresh() {
        val intent = Intent(this, TrainWidgetProvider::class.java).apply {
            action = ACTION_REFRESH
            putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
        }
        sendBroadcast(intent)
    }
}
