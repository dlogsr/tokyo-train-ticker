package com.tokyotrainticker.app

import android.content.Context

/**
 * Small SharedPreferences wrapper. Two scopes:
 *  - app-wide backend URL (used by MainActivity's WebView)
 *  - per-widget station id (each home-screen widget instance can watch a
 *    different station), keyed by appWidgetId
 */
object Prefs {
    private const val FILE = "tokyo_train_ticker_prefs"
    const val DEFAULT_BACKEND_URL = "https://tokyo-train-ticker-production.up.railway.app/"

    private const val KEY_BACKEND_URL = "backend_url"
    private const val KEY_STATION_PREFIX = "widget_station_"
    private const val KEY_STATION_NAME_PREFIX = "widget_station_name_"

    fun getBackendUrl(context: Context): String =
        prefs(context).getString(KEY_BACKEND_URL, "") ?: ""

    fun setBackendUrl(context: Context, url: String) {
        prefs(context).edit().putString(KEY_BACKEND_URL, url.trim()).apply()
    }

    fun getWidgetStationId(context: Context, appWidgetId: Int): String? =
        prefs(context).getString(KEY_STATION_PREFIX + appWidgetId, null)

    fun getWidgetStationName(context: Context, appWidgetId: Int): String =
        prefs(context).getString(KEY_STATION_NAME_PREFIX + appWidgetId, "") ?: ""

    fun setWidgetStation(context: Context, appWidgetId: Int, stationId: String, stationName: String) {
        prefs(context).edit()
            .putString(KEY_STATION_PREFIX + appWidgetId, stationId)
            .putString(KEY_STATION_NAME_PREFIX + appWidgetId, stationName)
            .apply()
    }

    fun removeWidget(context: Context, appWidgetId: Int) {
        prefs(context).edit()
            .remove(KEY_STATION_PREFIX + appWidgetId)
            .remove(KEY_STATION_NAME_PREFIX + appWidgetId)
            .apply()
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
}
