package com.hush.tv

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.DisplayMetrics
import android.view.Surface
import android.widget.Toast
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/**
 * Sends this phone's or tablet's screen to the Hush server as a live H.264 stream (the server turns it into video any Hush screen can play).
 * The screen is captured with MediaProjection, encoded by the phone's hardware, and POSTed as one long chunked request.
 */
class ShareService : Service() {
    private var projection: MediaProjection? = null
    private var display: VirtualDisplay? = null
    private var codec: MediaCodec? = null
    private var surface: Surface? = null
    private var conn: HttpURLConnection? = null
    private val queue = LinkedBlockingQueue<ByteArray>(90)
    @Volatile private var stopping = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) { stopSharing("Stopped sharing"); return START_NOT_STICKY }
        val url = intent?.getStringExtra("url") ?: return START_NOT_STICKY
        val token = intent.getStringExtra("token") ?: ""
        val device = intent.getStringExtra("device") ?: "Android"
        val code = intent.getIntExtra("code", 0)
        @Suppress("DEPRECATION") val data = intent.getParcelableExtra<Intent>("data") ?: return START_NOT_STICKY
        startForegroundNotice()
        try {
            val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            val proj = mpm.getMediaProjection(code, data)
            proj.registerCallback(object : MediaProjection.Callback() { override fun onStop() { stopSharing("Sharing stopped") } }, Handler(Looper.getMainLooper()))
            projection = proj
            begin(proj, url, token, device)
            running = true
        } catch (e: Exception) {
            stopSharing("Couldn't share the screen: ${e.message}")
        }
        return START_NOT_STICKY
    }

    private fun startForegroundNotice() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(NotificationChannel(CHANNEL, "Screen sharing", NotificationManager.IMPORTANCE_LOW))
        val stop = PendingIntent.getService(this, 1, Intent(this, ShareService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 23) PendingIntent.FLAG_IMMUTABLE else 0))
        val b = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL) else @Suppress("DEPRECATION") Notification.Builder(this)
        val n = b.setContentTitle("Sharing your screen to Hush").setContentText("Tap Stop to end it").setSmallIcon(android.R.drawable.presence_video_online)
            .addAction(Notification.Action.Builder(null, "Stop", stop).build()).setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION) else startForeground(1, n)
    }

    private fun begin(proj: MediaProjection, url: String, token: String, device: String) {
        val dm = DisplayMetrics()
        @Suppress("DEPRECATION") (getSystemService(Context.WINDOW_SERVICE) as android.view.WindowManager).defaultDisplay.getRealMetrics(dm)
        val scale = minOf(1.0, 1280.0 / maxOf(dm.widthPixels, dm.heightPixels))
        val w = (dm.widthPixels * scale).toInt() / 2 * 2
        val h = (dm.heightPixels * scale).toInt() / 2 * 2
        fun format(extras: Boolean) = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BIT_RATE, 3_000_000)
            setInteger(MediaFormat.KEY_FRAME_RATE, 30)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
            if (extras) {
                setLong("repeat-previous-frame-after", 100_000)        // a still screen still sends frames, so the picture never stalls
                if (Build.VERSION.SDK_INT >= 29) setInteger("prepend-sps-pps-to-idr-frames", 1)
            }
        }
        // Some encoders refuse the optional settings: try with them, then without.
        var enc = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        try { enc.configure(format(true), null, null, MediaCodec.CONFIGURE_FLAG_ENCODE) }
        catch (_: Exception) {
            try { enc.release() } catch (_: Exception) {}
            enc = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
            enc.configure(format(false), null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        }
        surface = enc.createInputSurface()
        enc.start()
        codec = enc
        display = proj.createVirtualDisplay("hush-share", w, h, dm.densityDpi, DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, surface, null, null)
        thread(name = "share-send") { send(url, token, device) }
        thread(name = "share-encode") { drain(enc) }
    }

    /** Encoded frames go to the queue; when the network cannot keep up, frames are dropped until the next key frame so the picture stays current. */
    private fun drain(enc: MediaCodec) {
        val info = MediaCodec.BufferInfo()
        var config: ByteArray? = null
        var dropping = false
        try {
            while (!stopping) {
                val i = enc.dequeueOutputBuffer(info, 200_000)
                if (i < 0) continue
                val buf = enc.getOutputBuffer(i)
                if (buf != null && info.size > 0) {
                    buf.position(info.offset); buf.limit(info.offset + info.size)
                    val bytes = ByteArray(info.size); buf.get(bytes)
                    val isConfig = info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG != 0
                    val isKey = info.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME != 0
                    if (isConfig) config = bytes
                    else {
                        if (isKey) dropping = false
                        if (!dropping) {
                            val out = if (isKey && config != null && !startsWithSps(bytes)) config + bytes else bytes     // the stream must carry its headers before every key frame
                            if (!queue.offer(out)) dropping = true
                        }
                    }
                    if (isConfig && queue.remainingCapacity() > 0) queue.offer(bytes)
                }
                enc.releaseOutputBuffer(i, false)
            }
        } catch (_: Exception) { /* stopped */ }
    }

    /** True when the first NAL unit of an Annex-B frame is an SPS (type 7). */
    private fun startsWithSps(b: ByteArray): Boolean {
        var i = 0
        while (i + 3 < b.size && !(b[i] == 0.toByte() && b[i + 1] == 0.toByte() && (b[i + 2] == 1.toByte() || (b[i + 2] == 0.toByte() && b[i + 3] == 1.toByte())))) i++
        i += if (i + 2 < b.size && b[i + 2] == 1.toByte()) 3 else 4
        return i < b.size && (b[i].toInt() and 0x1f) == 7
    }

    private fun send(url: String, token: String, device: String) {
        try {
            val c = URL(url).openConnection() as HttpURLConnection
            conn = c
            c.requestMethod = "POST"; c.doOutput = true; c.setChunkedStreamingMode(16384)
            c.connectTimeout = 8000; c.readTimeout = 0
            c.setRequestProperty("x-hush-token", token); c.setRequestProperty("x-hush-device", device)
            c.setRequestProperty("Content-Type", "video/h264")
            val out = c.outputStream
            while (!stopping) {
                val chunk = queue.poll(500, TimeUnit.MILLISECONDS) ?: continue
                out.write(chunk)
            }
            out.flush(); out.close()
        } catch (e: Exception) {
            if (!stopping) Handler(Looper.getMainLooper()).post { Toast.makeText(applicationContext, "Sharing stopped: ${e.message}", Toast.LENGTH_LONG).show() }
        } finally {
            stopSharing(null)
        }
    }

    private fun stopSharing(message: String?) {
        if (stopping) return
        stopping = true; running = false
        try { display?.release() } catch (_: Exception) {}
        try { codec?.stop(); codec?.release() } catch (_: Exception) {}
        try { surface?.release() } catch (_: Exception) {}
        try { projection?.stop() } catch (_: Exception) {}
        try { conn?.disconnect() } catch (_: Exception) {}
        if (message != null) Handler(Looper.getMainLooper()).post { Toast.makeText(applicationContext, message, Toast.LENGTH_SHORT).show() }
        stopForeground(true)
        stopSelf()
    }

    override fun onDestroy() { stopping = true; running = false; super.onDestroy() }

    companion object {
        const val ACTION_STOP = "com.hush.tv.STOP_SHARE"
        private const val CHANNEL = "share"
        @Volatile var running = false

        fun stop(context: Context) { context.startService(Intent(context, ShareService::class.java).setAction(ACTION_STOP)) }
    }
}
