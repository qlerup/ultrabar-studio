package dk.ultrabarx.notifications;

import android.content.Context;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;

final class Banner {
    private final Context context;
    private final WindowManager windows;
    private View visible;

    Banner(Context context) {
        this.context = context;
        windows = context.getSystemService(WindowManager.class);
    }

    void show(String source, String title, String message, String kind, long duration, Handler main) {
        if (visible != null) remove(visible);
        int accent = "success".equals(kind) ? 0xff96e2c9
                : "warning".equals(kind) ? 0xffffcd8b : 0xffc2b5ff;

        LinearLayout card = new LinearLayout(context);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(17), dp(13), dp(17), dp(14));
        card.setElevation(dp(8));
        card.setLayoutDirection(View.LAYOUT_DIRECTION_LOCALE);
        GradientDrawable surface = new GradientDrawable();
        surface.setColor(0xff20232e);
        surface.setCornerRadius(dp(16));
        surface.setStroke(dp(1), 0xff414759);
        card.setBackground(surface);
        TextView attribution = text(source, 12, accent, 1, true);
        TextView headline = text(title, 20, 0xfff6f7fc, 1, true);
        TextView detail = text(message, 15, 0xffd7dae6, 2, false);
        headline.setPadding(0, dp(3), 0, 0);
        detail.setPadding(0, dp(3), 0, 0);
        card.addView(attribution);
        card.addView(headline);
        card.addView(detail);

        DisplayMetrics display = new DisplayMetrics();
        windows.getDefaultDisplay().getMetrics(display);
        int margin = dp(14);
        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                Math.min(dp(420), display.widthPixels - 2 * margin),
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
                PixelFormat.TRANSLUCENT);
        params.gravity = Gravity.TOP | Gravity.RIGHT;
        params.x = margin;
        params.y = margin;
        // Android 12+ caps pass-through overlay opacity at 0.8.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) params.alpha = 0.8f;
        windows.addView(card, params);
        visible = card;
        main.postDelayed(() -> remove(card), duration);
    }

    private TextView text(String value, int size, int color, int lines, boolean bold) {
        TextView view = new TextView(context);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setMaxLines(lines);
        view.setEllipsize(TextUtils.TruncateAt.END);
        view.setTextDirection(View.TEXT_DIRECTION_FIRST_STRONG);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private int dp(int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    private void remove(View banner) {
        if (visible != banner) return;
        windows.removeView(banner);
        visible = null;
    }
}
