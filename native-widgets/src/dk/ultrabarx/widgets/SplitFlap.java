package dk.ultrabarx.widgets;

import android.animation.ValueAnimator;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.view.View;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Hinged pairs of numerals, using device time even when Studio disconnects. */
final class SplitFlap {
    private final Paint ink = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Typeface type = Typeface.create("sans-serif-condensed", Typeface.BOLD);
    private String key = "", digits = "", previous = "", date = "", period = "";
    private long tick = -1;

    void draw(View view, Canvas canvas, JSONObject spec, JSONObject face, String title, boolean small) {
        long now = System.currentTimeMillis(), second = now / 1000;
        boolean twelve = "12".equals(spec.optString("hourFormat"));
        boolean seconds = !small && spec.optBoolean("showSeconds", true);
        Locale locale = Locale.getDefault();
        String configuration = title + "/" + twelve + "/" + small + "/" + seconds + "/" + locale;
        if (second != tick || !key.equals(configuration)) {
            Date instant = new Date(now);
            String next = new SimpleDateFormat((twelve ? "hhmm" : "HHmm") + (seconds ? "ss" : ""), locale).format(instant);
            previous = second == tick + 1 && key.equals(configuration) ? digits : next;
            digits = next;
            period = twelve ? new SimpleDateFormat("a", locale).format(instant) : "";
            date = new SimpleDateFormat(small ? "d MMM" : "EEE, d MMM yyyy", locale).format(instant);
            key = configuration;
            tick = second;
        }
        int background = Color.parseColor(spec.optString("background", "#171919"));
        int foreground = Color.parseColor(spec.optString("textColor", "#f5f0df"));
        int accent = Color.parseColor(spec.optString("accent", "#dfb37b"));
        int plate = Color.parseColor(face.optString("plateColor", "#353839"));
        int duration = face.optInt("durationMs");
        float progress = duration == 0 || !ValueAnimator.areAnimatorsEnabled() ? 1f : Math.min(1f, (now % 1000) / (float)duration);
        float width = view.getWidth(), height = view.getHeight(), pad = width * .072f;
        canvas.drawColor(background);
        float tileHeight = height * (small ? .43f : .39f);
        float gap = width * .025f;
        float available = width - 2 * pad - gap * (seconds ? 2 : 1);
        float tileWidth = available / (seconds ? 2.64f : 2);
        float center = height * .52f, x = pad;
        for (int i = 0; i < digits.length(); i += 2) {
            float w = i == 4 ? tileWidth * .64f : tileWidth;
            float h = i == 4 ? tileHeight * .72f : tileHeight;
            float top = center + tileHeight / 2 - h;
            String value = digits.substring(i, i + 2), old = previous.substring(i, i + 2);
            canvas.save();
            canvas.translate(x, top);
            half(canvas, w, h, value, true, plate, foreground, 1);
            half(canvas, w, h, progress < 1 ? old : value, false, plate, foreground, 1);
            if (progress < 1 && !old.equals(value)) {
                float cosine = (float)Math.cos(Math.PI * progress);
                half(canvas, w, h, cosine > 0 ? old : value, cosine > 0, plate, foreground, Math.abs(cosine));
            }
            ink.setColor(background);
            canvas.drawRect(0, h/2 - .7f, w, h/2 + .7f, ink);
            canvas.restore();
            x += w + gap;
        }
        ink.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        ink.setTextAlign(Paint.Align.LEFT);
        ink.setTextSize(height * (small ? .105f : .066f));
        ink.setColor(foreground);
        String name = android.text.TextUtils.ellipsize(title, new android.text.TextPaint(ink),
                width - 2 * pad - ink.measureText(period) - gap, android.text.TextUtils.TruncateAt.END).toString();
        canvas.drawText(name, pad, height * .19f, ink);
        ink.setTextAlign(Paint.Align.RIGHT);
        ink.setColor(accent);
        canvas.drawText(period, width - pad, height * .19f, ink);
        if (spec.optBoolean("showDate", true)) {
            ink.setTextAlign(Paint.Align.LEFT);
            ink.setTextSize(height * (small ? .102f : .073f));
            canvas.drawText(date, pad, height * .87f, ink);
        }
        if (progress < 1 && !previous.equals(digits)) view.postInvalidateOnAnimation();
        else view.postInvalidateDelayed(1000 - now % 1000);
    }

    private void half(Canvas c, float w, float h, String value, boolean upper, int plate, int color, float scale) {
        c.save();
        c.scale(1, scale, w / 2, h / 2);
        c.clipRect(0, upper ? 0 : h/2, w, upper ? h/2 : h);
        ink.setColor(plate);
        c.drawRoundRect(0, 0, w, h, w * .075f, w * .075f, ink);
        if (!upper) { ink.setColor(0x26000000); c.drawRoundRect(0, 0, w, h, w * .075f, w * .075f, ink); }
        ink.setTypeface(type);
        ink.setTextAlign(Paint.Align.CENTER);
        ink.setColor(color);
        ink.setTextSize(h * .82f);
        if (ink.measureText(value) > w * .87f) ink.setTextSize(ink.getTextSize() * w * .87f / ink.measureText(value));
        c.drawText(value, w/2, h/2 - (ink.ascent() + ink.descent())/2, ink);
        c.restore();
    }
}
