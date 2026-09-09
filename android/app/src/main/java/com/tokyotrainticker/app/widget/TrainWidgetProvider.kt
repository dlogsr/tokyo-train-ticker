package com.tokyotrainticker.app.widget

import android.app.AlarmManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.os.SystemClock
import android.view.View
import android.widget.RemoteViews
import com.tokyotrainticker.app.BackendClient
import com.tokyotrainticker.app.MainActivity
import com.tokyotrainticker.app.Prefs
import com.tokyotrainticker.app.R
import com.tokyotrainticker.app.TrainDeparture
import java.util.concurrent.Executors

const val ACTION_REFRESH = "com.tokyotrainticker.app.widget.ACTION_REFRESH"
private const val REFRESH_INTERVAL_MS = 5 * 60 * 1000L // widget-side "near real time" refresh
private const val WIDE_MIN_WIDTH_DP = 180 // below this we use the 3-row compact layout

/**
 * Resizable (2x2 <-> 4x2) home-screen widget. Each instance shows next departures
 * for a station chosen in TrainWidgetConfigureActivity. Layout is picked per-instance
 * from its current width so it reads well at both sizes (see train_widget_info.xml).
 */
class TrainWidgetProvider : AppWidgetProvider() {

    private val executor = Executors.newCachedThreadPool()

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        for (id in appWidgetIds) refresh(context, appWidgetManager, id)
    }

    override fun onAppWidgetOptionsChanged(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetId: Int,
        newOptions: Bundle,
    ) {
        refresh(context, appWidgetManager, appWidgetId)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_REFRESH) {
            val appWidgetManager = AppWidgetManager.getInstance(context)
            val id = intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, -1)
            if (id != -1) {
                refresh(context, appWidgetManager, id)
            } else {
                val ids = appWidgetManager.getAppWidgetIds(
                    android.content.ComponentName(context, TrainWidgetProvider::class.java)
                )
                onUpdate(context, appWidgetManager, ids)
            }
        }
    }

    override fun onEnabled(context: Context) = schedulePeriodicRefresh(context)

    override fun onDisabled(context: Context) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        alarmManager.cancel(refreshPendingIntent(context, -1))
    }

    override fun onDeleted(context: Context, appWidgetIds: IntArray) {
        for (id in appWidgetIds) Prefs.removeWidget(context, id)
    }

    // ── rendering ────────────────────────────────────────────────────────────

    private fun refresh(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int) {
        val stationId = Prefs.getWidgetStationId(context, appWidgetId)
        val stationName = Prefs.getWidgetStationName(context, appWidgetId)
        val backendUrl = Prefs.getBackendUrl(context)
        val wide = isWide(appWidgetManager, appWidgetId)
        val layoutRes = if (wide) R.layout.widget_wide else R.layout.widget_compact
        val rowCount = if (wide) 4 else 3

        if (stationId == null || backendUrl.isBlank()) {
            val views = RemoteViews(context.packageName, layoutRes)
            views.setTextViewText(R.id.stationName, context.getString(R.string.app_name))
            hideAllRows(views, rowCount)
            views.setViewVisibility(R.id.emptyText, View.VISIBLE)
            views.setTextViewText(R.id.emptyText, context.getString(R.string.widget_not_configured))
            views.setOnClickPendingIntent(R.id.widgetRoot, openConfigurePendingIntent(context, appWidgetId))
            appWidgetManager.updateAppWidget(appWidgetId, views)
            return
        }

        // Show a stale-but-present frame immediately, then replace once the fetch returns.
        executor.execute {
            val departures = runCatching { BackendClient.fetchStationTrains(backendUrl, stationId) }.getOrDefault(emptyList())
            val views = buildViews(context, layoutRes, rowCount, wide, stationName, departures, appWidgetId)
            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }

    private fun buildViews(
        context: Context,
        layoutRes: Int,
        rowCount: Int,
        wide: Boolean,
        stationName: String,
        departures: List<TrainDeparture>,
        appWidgetId: Int,
    ): RemoteViews {
        val views = RemoteViews(context.packageName, layoutRes)
        views.setTextViewText(R.id.stationName, stationName.ifBlank { context.getString(R.string.app_name) })
        views.setOnClickPendingIntent(R.id.refreshButton, refreshPendingIntent(context, appWidgetId))
        views.setOnClickPendingIntent(R.id.widgetRoot, openAppPendingIntent(context))

        if (departures.isEmpty()) {
            hideAllRows(views, rowCount)
            views.setViewVisibility(R.id.emptyText, View.VISIBLE)
            views.setTextViewText(R.id.emptyText, context.getString(R.string.widget_no_data))
            return views
        }
        views.setViewVisibility(R.id.emptyText, View.GONE)

        for (i in 0 until rowCount) {
            val rowId = ROW_IDS[i]
            if (i >= departures.size) {
                views.setViewVisibility(rowId, View.GONE)
                continue
            }
            val d = departures[i]
            views.setViewVisibility(rowId, View.VISIBLE)
            views.setTextViewText(LINE_IDS[i], d.lineName)
            views.setInt(LINE_IDS[i], "setBackgroundColor", safeColor(d.color, "#444444"))
            views.setTextColor(LINE_IDS[i], safeColor(d.textColor, "#ffffff"))
            views.setTextViewText(DEST_IDS[i], d.destination)
            views.setTextViewText(ETA_IDS[i], if (d.etaMin <= 0) "now" else "${d.etaMin}m")
            if (wide) {
                val meta = buildString {
                    if (d.platform.isNotBlank()) append("Plt ${d.platform}")
                    if (d.delayMin > 0) {
                        if (isNotEmpty()) append(" · ")
                        append("+${d.delayMin}m")
                    }
                }
                views.setTextViewText(META_IDS[i], meta)
            }
        }
        return views
    }

    private fun hideAllRows(views: RemoteViews, rowCount: Int) {
        for (i in 0 until rowCount) views.setViewVisibility(ROW_IDS[i], View.GONE)
    }

    private fun safeColor(hex: String, fallback: String): Int =
        runCatching { Color.parseColor(hex) }.getOrElse { Color.parseColor(fallback) }

    private fun isWide(appWidgetManager: AppWidgetManager, appWidgetId: Int): Boolean {
        val options = appWidgetManager.getAppWidgetOptions(appWidgetId)
        val width = options.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, 0)
        return width >= WIDE_MIN_WIDTH_DP
    }

    // ── pending intents ──────────────────────────────────────────────────────

    private fun refreshPendingIntent(context: Context, appWidgetId: Int): PendingIntent {
        val intent = Intent(context, TrainWidgetProvider::class.java).apply {
            action = ACTION_REFRESH
            putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
        }
        return PendingIntent.getBroadcast(
            context, appWidgetId, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun openConfigurePendingIntent(context: Context, appWidgetId: Int): PendingIntent {
        val intent = Intent(context, TrainWidgetConfigureActivity::class.java).apply {
            putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        return PendingIntent.getActivity(
            context, appWidgetId, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun openAppPendingIntent(context: Context): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        return PendingIntent.getActivity(
            context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun schedulePeriodicRefresh(context: Context) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        alarmManager.setInexactRepeating(
            AlarmManager.ELAPSED_REALTIME,
            SystemClock.elapsedRealtime() + REFRESH_INTERVAL_MS,
            REFRESH_INTERVAL_MS,
            refreshPendingIntent(context, -1),
        )
    }

    companion object {
        private val ROW_IDS = intArrayOf(R.id.row1, R.id.row2, R.id.row3, R.id.row4)
        private val LINE_IDS = intArrayOf(R.id.row1Line, R.id.row2Line, R.id.row3Line, R.id.row4Line)
        private val DEST_IDS = intArrayOf(R.id.row1Dest, R.id.row2Dest, R.id.row3Dest, R.id.row4Dest)
        private val ETA_IDS = intArrayOf(R.id.row1Eta, R.id.row2Eta, R.id.row3Eta, R.id.row4Eta)
        // Meta (platform/delay) column only exists in widget_wide's row layout — only
        // read when rendering that layout (see `wide` guard in buildViews).
        private val META_IDS = intArrayOf(R.id.row1Meta, R.id.row2Meta, R.id.row3Meta, R.id.row4Meta)
    }
}
