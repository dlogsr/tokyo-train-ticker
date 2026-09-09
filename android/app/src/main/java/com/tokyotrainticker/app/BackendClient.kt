package com.tokyotrainticker.app

import android.util.Log
import org.json.JSONArray
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

private const val TAG = "BackendClient"
private const val TIMEOUT_MS = 8000

data class Station(
    val id: String,
    val nameEn: String,
    val nameJa: String,
)

data class TrainDeparture(
    val lineName: String,
    val color: String,
    val textColor: String,
    val destination: String,
    val platform: String,
    val delayMin: Int,
    val etaMin: Int,
)

/**
 * Minimal REST client for the FastAPI backend (see backend/main.py).
 * Deliberately dependency-free (HttpURLConnection + org.json, both part of the
 * Android platform) so both the app and the widget's background updater stay
 * lightweight — no Retrofit/OkHttp/Gson needed for a handful of GET calls.
 */
object BackendClient {

    /** Normalizes a user-entered backend URL, e.g. "myhost:8000" -> "http://myhost:8000". */
    fun normalizeBaseUrl(raw: String): String {
        var url = raw.trim().trimEnd('/')
        if (url.isEmpty()) return url
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "http://$url"
        }
        return url
    }

    fun fetchStations(baseUrl: String): List<Station> {
        val json = get("${normalizeBaseUrl(baseUrl)}/api/stations") ?: return emptyList()
        val arr = JSONArray(json)
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            Station(
                id = o.optString("id"),
                nameEn = o.optString("name_en"),
                nameJa = o.optString("name_ja"),
            )
        }.sortedBy { it.nameEn }
    }

    fun fetchStationTrains(baseUrl: String, stationId: String): List<TrainDeparture> {
        val json = get("${normalizeBaseUrl(baseUrl)}/api/trains/station/$stationId") ?: return emptyList()
        val arr = JSONArray(json)
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            TrainDeparture(
                lineName = o.optString("line_name"),
                color = o.optString("color", "#444444"),
                textColor = o.optString("text_color", "#ffffff"),
                destination = o.optString("destination"),
                platform = o.optString("platform"),
                delayMin = o.optInt("delay_min", 0),
                etaMin = o.optInt("eta_min", 0),
            )
        }.sortedBy { it.etaMin }
    }

    private fun get(urlString: String): String? {
        var connection: HttpURLConnection? = null
        return try {
            val url = URL(urlString)
            connection = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = TIMEOUT_MS
                readTimeout = TIMEOUT_MS
            }
            if (connection.responseCode != HttpURLConnection.HTTP_OK) {
                Log.w(TAG, "GET $urlString -> HTTP ${connection.responseCode}")
                return null
            }
            BufferedReader(InputStreamReader(connection.inputStream, StandardCharsets.UTF_8)).use { it.readText() }
        } catch (e: Exception) {
            Log.w(TAG, "GET $urlString failed: ${e.message}")
            null
        } finally {
            connection?.disconnect()
        }
    }

    private fun BufferedReader.readText(): String = readLines().joinToString("\n")
}
