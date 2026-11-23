package dk.ultrabarx.notifications;

import android.app.NotificationManager;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.Process;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Log;
import android.util.SparseLongArray;

public final class NotificationProvider extends ContentProvider {
    public static final String POST = "dk.ultrabarx.notifications.POST";
    private static final String LAUNCHER = "com.ultrabar.launch";
    private static final long DURATION_MS = 4_000;
    private static final long PER_APP_INTERVAL_MS = 12_000;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final SparseLongArray nextByUid = new SparseLongArray();
    private long nextBanner;
    private Banner banner;

    @Override
    public boolean onCreate() {
        banner = new Banner(getContext());
        return true;
    }

    @Override
    public Bundle call(String method, String arg, Bundle extras) {
        Context context = getContext();
        int uid = Binder.getCallingUid();
        boolean shell = uid == Process.SHELL_UID || uid == 0;
        if (shell && "status.v1".equals(method)) {
            return result(canDrawOverlays() ? "ready" : "overlay_unavailable");
        }
        if (shell && "test.v1".equals(method)) {
            int sound;
            if (arg == null || "silent".equals(arg)) sound = 0;
            else if ("complete".equals(arg)) sound = R.raw.print_complete;
            else if ("error".equals(arg)) sound = R.raw.print_error;
            else return result("invalid");
            return post(uid, "UltraBar Studio", "Core Notifications",
                    "This is a test notification from Studio.", "info", sound);
        }
        if (!"post.v1".equals(method)) return result("unknown_method");

        String caller = getCallingPackage();
        if (caller == null || !(LAUNCHER.equals(caller)
                || context.checkCallingPermission(POST) == PackageManager.PERMISSION_GRANTED)) {
            return result("permission_denied");
        }
        if (extras == null) return result("invalid");
        String title;
        String message;
        String kind;
        try {
            title = clean(extras.getString("title"), 80);
            message = clean(extras.getString("message"), 200);
            kind = extras.getString("kind", "info");
        } catch (RuntimeException malformed) {
            return result("invalid");
        }
        if (title.isEmpty() || message.isEmpty()
                || !("info".equals(kind) || "success".equals(kind) || "warning".equals(kind))) {
            return result("invalid");
        }
        PackageManager packages = context.getPackageManager();
        try {
            ApplicationInfo app = packages.getApplicationInfo(caller, 0);
            String label = clean(packages.getApplicationLabel(app).toString(), 48);
            return post(uid, label.isEmpty() ? caller : label, title, message, kind, 0);
        } catch (PackageManager.NameNotFoundException removed) {
            return result("permission_denied");
        }
    }

    private synchronized Bundle post(int uid, String source, String title, String message,
                                     String kind, int testSound) {
        Context context = getContext();
        PowerManager power = context.getSystemService(PowerManager.class);
        if (!power.isInteractive()) return result("screen_off");
        if (!canDrawOverlays()) return result("overlay_unavailable");
        long now = SystemClock.elapsedRealtime();
        if (now < nextBanner || now < nextByUid.get(uid)) return result("busy");
        nextBanner = now + DURATION_MS;
        nextByUid.put(uid, now + PER_APP_INTERVAL_MS);
        main.post(() -> {
            if (!power.isInteractive()) return;
            try {
                banner.show(source, title, message, kind, DURATION_MS, main);
                if (testSound != 0) playTestSound(context, testSound);
            } catch (SecurityException | android.view.WindowManager.BadTokenException error) {
                Log.w("CoreNotifications", "Unable to display a banner", error);
            }
        });
        return result("accepted");
    }

    private static void playTestSound(Context context, int resource) {
        AudioManager audio = context.getSystemService(AudioManager.class);
        NotificationManager notifications = context.getSystemService(NotificationManager.class);
        int filter = notifications.getCurrentInterruptionFilter();
        if (audio.getRingerMode() != AudioManager.RINGER_MODE_NORMAL
                || (filter != NotificationManager.INTERRUPTION_FILTER_ALL
                && filter != NotificationManager.INTERRUPTION_FILTER_UNKNOWN)) return;

        AudioAttributes attributes = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build();
        MediaPlayer player = null;
        try {
            player = MediaPlayer.create(context, resource, attributes, AudioManager.AUDIO_SESSION_ID_GENERATE);
            if (player == null) {
                Log.w("CoreNotifications", "Unable to open test sound");
                return;
            }
            player.setOnCompletionListener(MediaPlayer::release);
            player.setOnErrorListener((failed, what, extra) -> {
                Log.w("CoreNotifications", "Test sound playback failed: " + what + "/" + extra);
                failed.release();
                return true;
            });
            player.start();
        } catch (RuntimeException error) {
            if (player != null) player.release();
            Log.w("CoreNotifications", "Unable to play test sound", error);
        }
    }

    private boolean canDrawOverlays() {
        // Check the provider's permission, even when the caller is root or ADB shell.
        long identity = Binder.clearCallingIdentity();
        try {
            return Settings.canDrawOverlays(getContext());
        } finally {
            Binder.restoreCallingIdentity(identity);
        }
    }

    private static String clean(String value, int max) {
        if (value == null || value.length() > max * 2) return "";
        String cleaned = value.replaceAll("[\\p{Cc}\\p{Cf}\\s]+", " ").trim();
        int count = cleaned.codePointCount(0, cleaned.length());
        if (count > max) return "";
        return cleaned;
    }

    private static Bundle result(String status) {
        Bundle response = new Bundle();
        response.putString("status", status);
        return response;
    }

    @Override public Cursor query(Uri uri, String[] p, String s, String[] a, String o) {
        throw new UnsupportedOperationException();
    }
    @Override public String getType(Uri uri) { return null; }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String s, String[] a) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String s, String[] a) {
        throw new UnsupportedOperationException();
    }
}
