package dk.ultrabarx.notifications;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.Process;
import android.provider.Settings;
import android.util.Log;

public final class NotificationProvider extends ContentProvider {
    public static final String POST = "dk.ultrabarx.notifications.POST";
    private static final String LAUNCHER = "com.ultrabar.launch";
    private static final long DURATION_MS = 4_000;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final NotificationQueue<Runnable> queue = new NotificationQueue<>();
    private PowerManager power;
    private Banner banner;
    private TestSound testSound;

    @Override
    public boolean onCreate() {
        power = getContext().getSystemService(PowerManager.class);
        banner = new Banner(getContext());
        testSound = new TestSound(getContext(), main);
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
            String[] test = (arg == null ? "silent" : arg).split(":", 2);
            int sound;
            if ("silent".equals(test[0])) sound = 0;
            else if ("complete".equals(test[0])) sound = R.raw.print_complete;
            else if ("error".equals(test[0])) sound = R.raw.print_error;
            else return result("invalid");

            int percentage = -1;
            if (test.length == 2) {
                try {
                    percentage = Integer.parseInt(test[1]);
                } catch (NumberFormatException malformed) {
                    return result("invalid");
                }
                if (percentage < 0 || percentage > 100) return result("invalid");
            }
            return post(uid, "UltraBar Studio", "Core Notifications",
                    "This is a test notification from Studio.", "info", sound, percentage, true);
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
            return post(uid, label.isEmpty() ? caller : label, title, message, kind, 0, -1, false);
        } catch (PackageManager.NameNotFoundException removed) {
            return result("permission_denied");
        }
    }

    private Bundle post(int uid, String source, String title, String message, String kind,
                        int sound, int percentage, boolean studioTest) {
        if (!power.isInteractive()) return result("screen_off");
        if (!canDrawOverlays()) return result("overlay_unavailable");

        Runnable display = () -> {
            banner.show(source, title, message, kind, DURATION_MS, main);
            if (sound != 0) testSound.play(sound, percentage);
        };
        switch (queue.offer(uid, display)) {
            case START:
                main.post(() -> show(display));
                return result("accepted");
            case QUEUED:
                return result(studioTest ? "queued" : "accepted");
            case FULL:
                return result("busy");
        }
        throw new AssertionError("Unhandled queue result");
    }

    private void show(Runnable display) {
        if (!power.isInteractive()) {
            queue.clear();
            return;
        }
        try {
            display.run();
        } catch (SecurityException | android.view.WindowManager.BadTokenException error) {
            Log.w("CoreNotifications", "Unable to display a banner", error);
        } finally {
            main.postDelayed(() -> {
                Runnable next = queue.next();
                if (next != null) show(next);
            }, DURATION_MS);
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
