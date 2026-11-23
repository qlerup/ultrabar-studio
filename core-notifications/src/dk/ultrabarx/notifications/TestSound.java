package dk.ultrabarx.notifications;

import android.app.NotificationManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.os.Handler;
import android.util.Log;

/** Owns the notification stream adjustment for the short Studio test clip. */
final class TestSound {
    private static final String TAG = "CoreNotifications";
    private static final int STREAM = AudioManager.STREAM_NOTIFICATION;
    private static final long PLAYBACK_TIMEOUT_MS = 2_500;

    private final Context context;
    private final Handler main;
    private final AudioManager audio;
    private final SharedPreferences volume;
    private final Runnable timeout = this::finish;
    private MediaPlayer player;

    TestSound(Context context, Handler main) {
        this.context = context;
        this.main = main;
        audio = context.getSystemService(AudioManager.class);
        volume = context.getSharedPreferences("test_sound_volume", Context.MODE_PRIVATE);
        restoreVolume();
    }

    void play(int resource, int percentage) {
        if (percentage == 0) return;
        NotificationManager notifications = context.getSystemService(NotificationManager.class);
        int filter = notifications.getCurrentInterruptionFilter();
        if (audio.getRingerMode() != AudioManager.RINGER_MODE_NORMAL
                || (filter != NotificationManager.INTERRUPTION_FILTER_ALL
                && filter != NotificationManager.INTERRUPTION_FILTER_UNKNOWN)) return;

        finish();
        if (volume.contains("original")) return;
        try {
            AudioAttributes attributes = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build();
            player = MediaPlayer.create(context, resource, attributes, AudioManager.AUDIO_SESSION_ID_GENERATE);
            if (player == null) {
                Log.w(TAG, "Unable to open test sound");
                return;
            }
            player.setOnCompletionListener(completed -> {
                if (completed == player) finish();
            });
            player.setOnErrorListener((failed, what, extra) -> {
                Log.w(TAG, "Test sound playback failed: " + what + "/" + extra);
                if (failed == player) finish();
                return true;
            });
            if (percentage > 0 && !setVolume(percentage)) {
                finish();
                return;
            }
            main.postDelayed(timeout, PLAYBACK_TIMEOUT_MS);
            player.start();
        } catch (RuntimeException error) {
            Log.w(TAG, "Unable to play test sound", error);
            finish();
        }
    }

    private boolean setVolume(int percentage) {
        int original = audio.getStreamVolume(STREAM);
        int requested = Math.max(1, Math.round(audio.getStreamMaxVolume(STREAM) * percentage / 100f));
        if (original == requested) return true;
        // Persist the prior level before changing the device, so a process restart can recover it.
        if (!volume.edit().putInt("original", original).putInt("temporary", requested).commit()) {
            Log.w(TAG, "Unable to save test sound volume");
            return false;
        }
        audio.setStreamVolume(STREAM, requested, 0);
        return audio.getStreamVolume(STREAM) == requested;
    }

    private void finish() {
        main.removeCallbacks(timeout);
        MediaPlayer finished = player;
        player = null;
        try {
            if (finished != null) finished.release();
        } finally {
            restoreVolume();
        }
    }

    private void restoreVolume() {
        if (!volume.contains("original")) return;
        try {
            int original = volume.getInt("original", 0);
            // Preserve a volume change made on the device during the test.
            if (audio.getStreamVolume(STREAM) == volume.getInt("temporary", -1)) {
                audio.setStreamVolume(STREAM, original, 0);
                if (audio.getStreamVolume(STREAM) != original) {
                    Log.w(TAG, "Unable to restore test sound volume");
                    return;
                }
            }
            if (!volume.edit().clear().commit()) Log.w(TAG, "Unable to clear saved test sound volume");
        } catch (RuntimeException error) {
            Log.w(TAG, "Unable to restore test sound volume", error);
        }
    }
}
