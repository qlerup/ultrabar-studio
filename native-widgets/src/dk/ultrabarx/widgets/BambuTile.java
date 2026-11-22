package dk.ultrabarx.widgets;

import android.animation.*;
import android.app.AlertDialog;
import android.content.*;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.view.animation.LinearInterpolator;
import android.widget.*;
import org.json.*;
import java.util.ArrayList;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Model-independent Core home tile. Studio owns connections and credentials. */
public final class BambuTile {
    private static final Handler main = new Handler(Looper.getMainLooper());
    private static volatile JSONObject printers = new JSONObject();
    private static volatile JSONObject widgetSpecs = new JSONObject();
    private static volatile JSONObject printerImages = new JSONObject();
    private static final android.util.LruCache<String, Bitmap> thumbnails = new android.util.LruCache<>(16);
    private static volatile long received;
    private static WaterLayer expanded;
    private static final java.util.ArrayDeque<JSONObject> commands = new java.util.ArrayDeque<>();
    private static final int WHITE = 0xffeff6fa, MUTED = 0xff96aab5, MINT = 0xff86e4c3;
    private static final Pattern TOOL_TEMPERATURE = Pattern.compile("(T[0-9]+) ([0-9]+) / [0-9]+Â?°");
    public static void update(JSONObject data, long timestamp) {
        printers = data == null ? new JSONObject() : data; received = timestamp;
        main.post(() -> { if (expanded != null) expanded.refresh(); });
    }
    public static void updateSpecs(JSONObject specs){widgetSpecs=specs==null?new JSONObject():specs;}
    private static volatile JSONObject sceneImages = new JSONObject();
    static void updateSceneImages(JSONObject images){sceneImages=images==null?new JSONObject():images;}
    static void updateArtwork(JSONObject images) { printerImages = images == null ? new JSONObject() : images; }

    private static Bitmap thumbnail(JSONObject snapshot) {
        String encoded = printerImages.optString(snapshot.optString("model"));
        if (encoded.isEmpty() || encoded.length() > 8192) return null;
        Bitmap image = thumbnails.get(encoded);
        if (image != null) return image;
        try {
            byte[] bytes = android.util.Base64.decode(encoded, android.util.Base64.NO_WRAP);
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
            if (bounds.outWidth < 1 || bounds.outHeight < 1 || bounds.outWidth > 100 || bounds.outHeight > 100) return null;
            image = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
            if (image != null) thumbnails.put(encoded, image);
            return image;
        } catch (IllegalArgumentException invalidImage) {
            return null;
        }
    }
    private static JSONObject snapshot(JSONObject spec) {
        JSONObject value = printers.optJSONObject(spec.optString("printerId"));
        return value == null ? new JSONObject() : value;
    }
    public static synchronized String drainActions() {
        JSONArray result = new JSONArray();
        while (!commands.isEmpty()) {
            JSONObject command = commands.removeFirst();
            if (Math.abs(System.currentTimeMillis()-command.optLong("createdAt")) < 3000) result.put(command);
        }
        return result.toString();
    }
    private static boolean fresh(JSONObject s) { return received > 0 && SystemClock.elapsedRealtime()-received < 7000 && s.optBoolean("fresh"); }
    private static String state(JSONObject s) {
        if (!fresh(s)) return s.has("connection") ? "Offline" : "Choose printer in Studio";
        switch(s.optString("gcode_state")) {
            case "RUNNING": return "Printing"; case "PAUSE": return "Paused"; case "PREPARE": return "Preparing";
            case "FINISH": return "Complete"; case "FAILED": return "Stopped"; case "IDLE": return "Ready"; default: return "Connected";
        }
    }
    private static String metric(JSONObject s, String field) {
        if (field.equals("state")) return state(s);
        if (!fresh(s)) return "—";
        switch(field) {
            case "progress": return s.has("mc_percent") ? Math.max(0,Math.min(100,s.optInt("mc_percent")))+"%" : "—";
            case "remaining": return s.has("mc_remaining_time")&&s.optInt("mc_remaining_time")>=0 ? s.optInt("mc_remaining_time")/60+"h "+s.optInt("mc_remaining_time")%60+"m" : "—";
            case "temperature": return temperature(s, "nozzle_temper");
            case "job": return s.optString("subtask_name", "No active job");
            case "layers": return s.has("layer_num") ? "Layer "+s.optInt("layer_num")+" / "+s.optInt("total_layer_num") : "Layer —";
            case "none": return ""; default: return "—";
        }
    }
    static String smallTitle(JSONObject spec, String fallback) {
        return snapshot(spec).optString("name", fallback);
    }
    static String smallReading(JSONObject spec) {
        JSONObject printer = snapshot(spec);
        return fresh(printer) ? metric(printer, spec.optString("primary", "progress")) :
                printer.has("connection") ? "Offline" : "Setup";
    }
    static double smallProgress(JSONObject spec) {
        JSONObject printer = snapshot(spec);
        return fresh(printer) ? printer.optDouble("mc_percent") : Double.NaN;
    }
    private static String temperature(JSONObject s, String key) {
        double degrees = s.optDouble(key);
        return Double.isNaN(degrees) || Double.isInfinite(degrees) ? "—" : Math.round(degrees) + "°C";
    }
    private static void label(Canvas canvas, Paint paint, String text, float x, float y, float size, int color, boolean bold, float maxWidth) {
        paint.setColor(color); paint.setTextSize(size); paint.setTypeface(Typeface.create(bold?"sans-serif-medium":"sans-serif",Typeface.NORMAL));
        while (paint.measureText(text) > maxWidth && text.length() > 2) text = text.substring(0,text.length()-2)+"…";
        canvas.drawText(text, x, y, paint);
    }
    private static float cornerRadius(View source){
        View view=source;
        while(view!=null&&view.getHeight()<=source.getHeight()+2){
            try{Outline outline=new Outline();if(view.getOutlineProvider()!=null){view.getOutlineProvider().getOutline(view,outline);if(outline.getRadius()>0)return outline.getRadius();}}catch(Exception ignored){}
            ViewParent parent=view.getParent();view=parent instanceof View?(View)parent:null;
        }
        return source.getHeight()*.25f;
    }
    public static void draw(View source, Canvas canvas, float width, JSONObject spec, String title) {
        Paint p = new Paint(3); JSONObject s = snapshot(spec);
        int background = Color.parseColor(spec.optString("background", "#14202b"));
        int accent = Color.parseColor(spec.optString("accent", "#86e4c3"));
        int text = Color.parseColor(spec.optString("textColor", "#eff6fa"));
        RectF box = new RectF(1,1,width-1,239);
        float radius=cornerRadius(source)/(source.getHeight()/240f);
        p.setShader(new LinearGradient(0,0,width,240,new int[]{background,Color.rgb(Color.red(background)+Math.min(4,255-Color.red(background)), Color.green(background)+Math.min(5,255-Color.green(background)), Color.blue(background)+Math.min(8,255-Color.blue(background)))},null,Shader.TileMode.CLAMP));
        canvas.drawRoundRect(box,radius,radius,p); p.setShader(null);
        p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(1); p.setColor(0x26ffffff); canvas.drawRoundRect(box,radius,radius,p); p.setStyle(Paint.Style.FILL);
        p.setColor(fresh(s)?accent:0xff74838b); canvas.drawCircle(24,28,3,p);
        label(canvas,p,s.optString("name",title==null?"Bambu Lab":title),34,33,14,text,true,width-62);
        String primary = spec.optString("primary","progress"), value = metric(s,primary);
        Bitmap image = width >= 180 ? thumbnail(s) : null;
        boolean showArtwork = width >= 180 && (image != null || WidgetPresentation.hasArtwork(spec));
        float size = Math.min(86, width * .34f);
        float artworkX = width - 18 - size;
        float readingWidth = showArtwork ? artworkX - 30 : width - 42;
        if (primary.equals("progress")) {
            p.setColor(text);
            p.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
            p.setTextSize(52);
            p.setTextSize(BambuPresentation.fittedTextSize(p.getTextSize(), p.measureText(value), readingWidth));
            canvas.drawText(value, 22, 108, p);
        } else {
            label(canvas,p,value,22,108,30,text,true,readingWidth);
        }
        if (image != null) {
            float scale = size / Math.max(image.getWidth(), image.getHeight());
            float imageWidth = image.getWidth() * scale, imageHeight = image.getHeight() * scale;
            float left = artworkX + (size - imageWidth) / 2, top = 56 + (size - imageHeight) / 2;
            p.setFilterBitmap(true);
            canvas.drawBitmap(image, null, new RectF(left, top, left + imageWidth, top + imageHeight), p);
        } else if (showArtwork) {
            WidgetPresentation.draw(canvas, spec, artworkX, 56, size, accent);
        }
        label(canvas,p,primary.equals("progress")?state(s):primary.equals("remaining")?"TIME REMAINING":primary.equals("temperature")?"ACTIVE NOZZLE":"PRINTER STATUS",23,133,11,accent,false,readingWidth);
        String secondary = spec.optString("secondary", "remaining");
        label(canvas,p,(secondary.equals("temperature") ? "Nozzle " : "") + metric(s,secondary),23,165,14,MUTED,false,width-42);
        p.setColor(0x22ffffff); canvas.drawRoundRect(22,183,width-22,187,2,2,p);
        float percent = fresh(s)?Math.max(0,Math.min(100,s.optInt("mc_percent"))):0;
        p.setColor(accent); canvas.drawRoundRect(22,183,22+(width-44)*percent/100,187,2,2,p);
        label(canvas,p,"Tap to unfold",23,218,11,MUTED,false,width-64);
        label(canvas,p,"↗",width-40,219,18,accent,false,24);
    }
    private static synchronized void execute(Context context, JSONObject spec, String action) {
        JSONObject state = snapshot(spec);
        if (!fresh(state) || !spec.optBoolean("showControls",true) || !state.optBoolean("can_"+action) || commands.size() >= 16) {
            Toast.makeText(context,"Unavailable. Check printer status and enable controls in Studio.",Toast.LENGTH_LONG).show(); return;
        }
        try {
            commands.add(new JSONObject().put("id",java.util.UUID.randomUUID().toString().replace("-",""))
                .put("widgetId",spec.optString("_widgetId")).put("printerId",spec.optString("printerId"))
                .put("action",action).put("createdAt",System.currentTimeMillis()));
            Toast.makeText(context,"Request sent to Studio; waiting for printer",Toast.LENGTH_LONG).show();
        } catch(JSONException e) { Toast.makeText(context,"Printer request unavailable",Toast.LENGTH_LONG).show(); }
    }
    public static void expand(View source, JSONObject spec) {
        if (expanded != null) { expanded.close(); return; }
        View content = source.getRootView().findViewById(android.R.id.content);
        if (!(content instanceof ViewGroup)) return;
        ViewGroup host = (ViewGroup)content;
        expanded = new WaterLayer(source,host,spec); host.addView(expanded,new ViewGroup.LayoutParams(-1,-1)); expanded.open();
    }
    private static final class WaterLayer extends FrameLayout {
        private final View source; private final ViewGroup host; private final JSONObject spec;
        private final int foreground,accent,background,muted;
        private final Paint paint = new Paint(3); private final Path path = new Path();
        private final RectF from = new RectF(), to = new RectF(), current = new RectF();
        private final LinearLayout body, hero, temperatures, sideColumn, actions;
        private TextView name, status, value, job, details, controlHint;
        private final ArrayList<TemperatureTile> temperatureTiles = new ArrayList<>();
        private View packageView;
        private JSONObject packageFrame;
        private boolean shortToolLabels;
        private TextView environment;
        private Button pause, stop, light;
        private ProgressBar progress;
        private ValueAnimator animator;
        private float fraction; private boolean closing;
        private float radius;
        private final ArrayList<View> neighbors=new ArrayList<>();
        private final ArrayList<Float> translations=new ArrayList<>(),movements=new ArrayList<>();
        private View sourceItem;private float sourceAlpha;
        private boolean restored;
        WaterLayer(View source, ViewGroup host, JSONObject spec) {
            super(source.getContext()); this.source=source;this.host=host;this.spec=spec;
            foreground=Color.parseColor(spec.optString("textColor","#eff6fa"));accent=Color.parseColor(spec.optString("accent","#86e4c3"));background=Color.parseColor(spec.optString("background","#14202b"));
            muted=Color.rgb((int)(Color.red(foreground)*.62f+Color.red(background)*.38f),(int)(Color.green(foreground)*.62f+Color.green(background)*.38f),(int)(Color.blue(foreground)*.62f+Color.blue(background)*.38f));
            setWillNotDraw(false);setFocusableInTouchMode(true);setContentDescription("Expanded Bambu printer controls");requestFocus();
            int[] origin=new int[2],base=new int[2];source.getLocationOnScreen(origin);host.getLocationOnScreen(base);
            from.set(origin[0]-base[0],origin[1]-base[1],origin[0]-base[0]+source.getWidth(),origin[1]-base[1]+source.getHeight());
            radius=cornerRadius(source);
            ViewGroup row=null;View item=source;
            ViewParent ancestor=source.getParent();
            while(ancestor instanceof ViewGroup){ViewGroup v=(ViewGroup)ancestor;if(v.getClass().getName().contains("RecyclerView")||(v instanceof LinearLayout&&((LinearLayout)v).getOrientation()==LinearLayout.HORIZONTAL&&v.getChildCount()>1)){row=v;break;}item=v;ancestor=v.getParent();}
            float unit=from.width(),gap=source.getHeight()/12f,viewportLeft=gap,viewportWidth=host.getWidth()-gap*2;
            boolean mixed = source.getHeight() < 160;
            if (row != null) for (int i = 0; i < row.getChildCount(); i++) {
                View card = row.getChildAt(i);
                if (card.getHeight() > 0 && card.getHeight() < 160) mixed = true;
            }
            if(row!=null && !mixed){
                ArrayList<View> ordered=new ArrayList<>();
                for(int i=0;i<row.getChildCount();i++){View v=row.getChildAt(i);if(v.getWidth()>0&&v.getHeight()>=source.getHeight()*.8f){ordered.add(v);unit=Math.min(unit,v.getWidth());}}
                ordered.sort((a,b)->Float.compare(a.getX(),b.getX()));float measured=Float.MAX_VALUE;
                for(int i=1;i<ordered.size();i++){View a=ordered.get(i-1),b=ordered.get(i);float g=b.getX()-(a.getX()+a.getWidth());if(g>0)measured=Math.min(measured,g);}
                if(measured<Float.MAX_VALUE)gap=measured;
                int[] rowPosition=new int[2];row.getLocationOnScreen(rowPosition);viewportLeft=rowPosition[0]-base[0]+Math.max(gap,row.getPaddingLeft());
                int visibleSlots=Math.max(2,Math.round((row.getWidth()-gap*2+gap)/(unit+gap)));
                viewportWidth=unit*visibleSlots+gap*(visibleSlots-1);
                sourceItem=item;sourceAlpha=item.getAlpha();
            }
            int slots=spec.optInt("expandedSlots",3),visibleSlots=Math.max(slots,Math.round((viewportWidth+gap)/(unit+gap)));
            int position=Math.max(0,Math.min(visibleSlots-1,Math.round((from.left-viewportLeft)/(unit+gap))));
            float width=LiquidGeometry.width(unit,gap,viewportWidth,slots);
            float left=viewportLeft+LiquidGeometry.startSlot(position,slots,visibleSlots)*(unit+gap);
            if (mixed) {
                gap = 20;
                unit = (host.getWidth() - gap * 6) / 5;
                width = LiquidGeometry.width(unit, gap, host.getWidth() - gap * 2, slots);
                left = Math.max(gap, Math.min(host.getWidth() - gap - width, from.centerX() - width / 2));
                to.set(left, gap, left + width, host.getHeight() - gap);
                sourceItem = item;
                sourceAlpha = item.getAlpha();
                radius = Math.min(radius, from.height() / 4);
            } else to.set(left,from.top,left+width,from.bottom);
            current.set(from);
            if(row!=null && !mixed){for(int i=0;i<row.getChildCount();i++){View neighbor=row.getChildAt(i);if(neighbor==sourceItem)continue;int[] pos=new int[2];neighbor.getLocationOnScreen(pos);float x=pos[0]-base[0];float movement=x<from.left?to.left-from.left:to.right-from.right;neighbors.add(neighbor);translations.add(neighbor.getTranslationX());movements.add(movement);}}
            body=new LinearLayout(getContext());body.setOrientation(LinearLayout.VERTICAL);body.setPadding(30,14,30,14);
            FrameLayout.LayoutParams bp=new FrameLayout.LayoutParams((int)to.width(),(int)to.height());bp.leftMargin=(int)to.left;bp.topMargin=(int)to.top;addView(body,bp);
            LinearLayout header=new LinearLayout(getContext());header.setGravity(Gravity.CENTER_VERTICAL);
            name=txt("Bambu Lab",16,foreground,true);header.addView(name,new LinearLayout.LayoutParams(0,32,1));
            status=txt("LOCAL",11,accent,false);header.addView(status);
            body.addView(header);
            View handle=new View(getContext()){
                protected void onDraw(Canvas c){Paint p=new Paint(3);p.setColor(muted);c.drawRoundRect(getWidth()/2f-16,3,getWidth()/2f+16,6,2,2,p);}
            };
            handle.setContentDescription("Close printer details. Swipe down or activate to close.");
            handle.setOnClickListener(v->close());
            FrameLayout.LayoutParams handleParams=new FrameLayout.LayoutParams(64,20);
            handleParams.leftMargin=(int)(to.centerX()-32);handleParams.topMargin=(int)to.top+1;
            addView(handle,handleParams);
            LinearLayout middle=new LinearLayout(getContext());middle.setGravity(Gravity.CENTER_VERTICAL);
            hero=new LinearLayout(getContext());hero.setOrientation(LinearLayout.VERTICAL);
            LinearLayout headline=new LinearLayout(getContext());headline.setGravity(Gravity.CENTER_VERTICAL);
            value=txt("—",42,foreground,true);headline.addView(value,new LinearLayout.LayoutParams(0,-2,1));
            hero.addView(headline);
            job=txt("No active print",13,foreground,false);
            job.setEllipsize(android.text.TextUtils.TruncateAt.MARQUEE);job.setMarqueeRepeatLimit(-1);job.setSelected(true);
            LinearLayout jobLine = new LinearLayout(getContext());
            jobLine.setWeightSum(2);
            jobLine.addView(job, new LinearLayout.LayoutParams(0, -2, 1));
            hero.addView(jobLine, new LinearLayout.LayoutParams(-1, -2));
            progress=new ProgressBar(getContext(),null,android.R.attr.progressBarStyleHorizontal);progress.setMax(100);progress.setProgressTintList(android.content.res.ColorStateList.valueOf(accent));LinearLayout.LayoutParams progressParams=new LinearLayout.LayoutParams(-1,4);progressParams.setMargins(0,8,18,6);hero.addView(progress,progressParams);
            details=txt("Waiting for printer",12,muted,false);hero.addView(details);
            environment=txt("",12,muted,false);
            environment.setVisibility(GONE);
            hero.addView(environment);
            middle.addView(hero,new LinearLayout.LayoutParams(0,-2,1.15f));
            temperatures=new LinearLayout(getContext());temperatures.setOrientation(LinearLayout.VERTICAL);temperatures.setPadding(12,0,0,0);
            middle.addView(temperatures,new LinearLayout.LayoutParams(0,-2,1));
            sideColumn=new LinearLayout(getContext());
            sideColumn.setOrientation(LinearLayout.VERTICAL);
            sideColumn.setPadding(6,0,0,0);
            sideColumn.setVisibility(GONE);
            middle.addView(sideColumn,new LinearLayout.LayoutParams(0,-1));
            body.addView(middle,new LinearLayout.LayoutParams(-1,0,1));
            controlHint=txt("",11,muted,false);body.addView(controlHint);
            actions=new LinearLayout(getContext());
            pause=btn("Ⅱ  Pause",accent,()->execute(getContext(),spec,snapshot(spec).optString("gcode_state").equals("PAUSE")?"resume":"pause"));
            stop=btn("■  Stop",0xffffa6ab,()->new AlertDialog.Builder(getContext()).setTitle("Stop this print?").setMessage("The current print will end and cannot be resumed.").setNegativeButton("Keep printing",null).setPositiveButton("Stop print",(d,w)->execute(getContext(),spec,"stop")).show());
            light=btn("◉  Light",foreground,()->execute(getContext(),spec,snapshot(spec).optString("light").equals("on")?"light_off":"light_on"));
            for(Button button:new Button[]{pause,stop,light}){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,42,1);p.setMargins(0,0,6,0);actions.addView(button,p);}
            body.addView(actions);
            packageView=new View(getContext()){
                protected void onDraw(Canvas canvas){
                    if(packageFrame!=null)PackageScene.draw(this,canvas,packageFrame,sceneImages);
                }
            };
            packageView.setVisibility(GONE);
            body.addView(packageView,0,new LinearLayout.LayoutParams(-1,0,1));
            refresh();
            setOnKeyListener((v,key,event)->{if(key==KeyEvent.KEYCODE_BACK){if(event.getAction()==KeyEvent.ACTION_UP)close();return true;}return false;});
        }
        private TextView txt(String s,int size,int color,boolean bold){TextView v=new TextView(getContext());v.setText(s);v.setTextColor(color);v.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX,size);v.setSingleLine(true);v.setEllipsize(android.text.TextUtils.TruncateAt.END);if(bold)v.setTypeface(Typeface.create("sans-serif-medium",0));return v;}
        private final class TemperatureTile extends LinearLayout {
            final TextView label, reading;
            TextView filament;
            View swatch;
            String lastColor = "";

            TemperatureTile(int tint, int rowHeight, int materialSize, int swatchSize) {
                super(WaterLayer.this.getContext());
                setOrientation(VERTICAL);
                setGravity(Gravity.CENTER);
                setPadding(4, 0, 4, 0);
                GradientDrawable background = new GradientDrawable();
                background.setColor(0x0bffffff);
                background.setCornerRadius(18);
                background.setStroke(1, 0x10ffffff);
                setBackground(background);

                label = txt("", 11, tint, true);
                label.setHorizontallyScrolling(false);
                label.setGravity(Gravity.CENTER);
                label.setAutoSizeTextTypeUniformWithConfiguration(8, 11, 1, android.util.TypedValue.COMPLEX_UNIT_PX);
                boolean grid = rowHeight == 0;
                LinearLayout headline = new LinearLayout(getContext());
                if (grid) {
                    headline.setGravity(Gravity.CENTER);
                    headline.addView(label);
                    addView(headline,new LinearLayout.LayoutParams(-1,0,1));
                } else addView(label, new LinearLayout.LayoutParams(-1, 15));

                reading = txt("—", 26, foreground, true);
                reading.setHorizontallyScrolling(false);
                reading.setGravity(Gravity.CENTER);
                reading.setAutoSizeTextTypeUniformWithConfiguration(12, 26, 1, android.util.TypedValue.COMPLEX_UNIT_PX);
                if (grid) {
                    reading.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX,16);
                    headline.addView(reading,new LinearLayout.LayoutParams(-2,-1));
                    reading.setPadding(5,0,0,0);
                    LinearLayout footer=new LinearLayout(getContext());
                    footer.setGravity(Gravity.CENTER);
                    filament=txt("",materialSize,foreground,true);
                    filament.setGravity(Gravity.CENTER);
                    filament.setHorizontallyScrolling(false);
                    filament.setAutoSizeTextTypeUniformWithConfiguration(9,materialSize,1,android.util.TypedValue.COMPLEX_UNIT_PX);
                    footer.addView(filament,new LinearLayout.LayoutParams(-2,-1));
                    swatch=new View(getContext());
                    LinearLayout.LayoutParams chip=new LinearLayout.LayoutParams(swatchSize,swatchSize);
                    chip.leftMargin=to.width()<640 ? 4 : 8;
                    footer.addOnLayoutChangeListener((v,l,t,r,b,ol,ot,oright,ob)->{
                        if(r-l!=oright-ol) filament.setMaxWidth(Math.max(1,r-l-swatchSize-chip.leftMargin));
                    });
                    footer.addView(swatch,chip);
                    addView(footer,new LinearLayout.LayoutParams(-1,Math.max(materialSize+6,swatchSize+4)));
                    setPadding(2,1,2,2);
                } else addView(reading, new LinearLayout.LayoutParams(-1, Math.min(36, rowHeight - 15)));
            }

            void showFilament(String material,String color) {
                if (filament==null) return;
                filament.setText(material.isEmpty() ? "—" : material);
                swatch.setVisibility(color.isEmpty() ? GONE : VISIBLE);
                if (!color.isEmpty() && !color.equals(lastColor)) {
                    GradientDrawable chip=new GradientDrawable();
                    chip.setCornerRadius(2);
                    chip.setColor(Color.parseColor(color));
                    chip.setStroke(1,0x88ffffff);
                    swatch.setBackground(chip);
                    swatch.setContentDescription(color);
                }
                lastColor=color;
            }

            void show(String title, String value) {
                if (!title.contentEquals(label.getText())) label.setText(title);
                if (!value.contentEquals(reading.getText())) reading.setText(value);
            }
        }

        private String lastSideFields = "";
        private int lastMinimumRows, lastMaterialSize, lastSwatchSize, lastInset;
        private void layoutTemperatures(int nozzleCount) {
            int total = nozzleCount + 2;
            JSONObject current = widgetSpecs.optJSONObject(spec.optString("_widgetId"));
            JSONObject presentation = (current == null ? spec : current).optJSONObject("_presentation");
            int minimum = presentation == null ? 1 : Math.max(1, Math.min(3, presentation.optInt("minTemperatureRows", 1)));
            boolean grid = minimum > 1;
            JSONObject style = grid ? presentation.optJSONObject("nozzleGrid") : null;
            int materialSize = style == null ? 11 : style.optInt("materialSize",11);
            int swatchSize = style == null ? 9 : style.optInt("swatchSize",9);
            int inset = style == null ? 14 : style.optInt("verticalInset",14);
            JSONArray sideFields = style == null ? null : style.optJSONArray("sideTemperatures");
            String sideKey = sideFields == null ? "" : sideFields.toString();
            if (sideKey.equals(lastSideFields) && materialSize == lastMaterialSize && swatchSize == lastSwatchSize && inset == lastInset
                    && temperatureTiles.size() == (grid ? nozzleCount : total) && minimum == lastMinimumRows) return;
            lastSideFields = sideKey;
            sideColumn.removeAllViews();
            int sideWidth = sideFields == null ? 0 : Math.min(192,Math.round(to.width()*.15f));
            sideColumn.getLayoutParams().width = sideWidth;
            if(sideFields!=null){
                for(int i=0;i<sideFields.length();i++){
                    TemperatureTile tile=new TemperatureTile(0xffc7ddeb,72,materialSize,swatchSize);
                    tile.setTag(sideFields.optString(i));
                    LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,0,1);
                    if(i>0)lp.topMargin=4;
                    sideColumn.addView(tile,lp);
                }
            }
            lastMinimumRows = minimum;
            lastMaterialSize = materialSize;
            lastSwatchSize = swatchSize;
            lastInset = inset;
            body.setPadding(30,inset,30,inset);
            ViewGroup.LayoutParams nameParams = name.getLayoutParams();
            nameParams.height = Math.max(24,18+inset);
            name.setLayoutParams(nameParams);
            temperatureTiles.clear();
            temperatures.removeAllViews();

            float weight = nozzleCount > 2 ? 2.5f : nozzleCount == 2 ? 1.45f : 1f;
            LinearLayout.LayoutParams params = (LinearLayout.LayoutParams) temperatures.getLayoutParams();
            params.weight = weight;
            params.height = grid ? -1 : -2;
            temperatures.setLayoutParams(params);
            float heroWeight = sideWidth > 0 && to.width()<640 ? .8f : 1.15f;
            LinearLayout.LayoutParams heroParams = (LinearLayout.LayoutParams) hero.getLayoutParams();
            heroParams.weight = heroWeight;
            hero.setLayoutParams(heroParams);
            float width = (to.width() - sideWidth - body.getPaddingLeft() - body.getPaddingRight()) * weight / (heroWeight + weight) - temperatures.getPaddingLeft();
            if (grid) {
                int rows = Math.min(minimum,nozzleCount);
                int columns = (nozzleCount + rows - 1) / rows;
                shortToolLabels = width / columns < (sideWidth > 0 ? 120 : 96);
                for (int r=0;r<rows;r++) {
                    LinearLayout row = new LinearLayout(getContext());
                    LinearLayout.LayoutParams rp = new LinearLayout.LayoutParams(-1,0,1);
                    if (r>0) rp.topMargin=3;
                    temperatures.addView(row,rp);
                    for (int col=0;col<columns;col++) {
                        LinearLayout.LayoutParams cp=new LinearLayout.LayoutParams(0,-1,1);
                        if(col>0)cp.leftMargin=3;
                        if(r*columns+col < nozzleCount){
                            TemperatureTile tile=new TemperatureTile(0xffffbc8c,0,materialSize,swatchSize);
                            row.addView(tile,cp);
                            temperatureTiles.add(tile);
                        }else row.addView(new View(getContext()),cp);
                    }
                }
                return;
            }
            int columns = Math.max((total + 2) / 3, (int) (width / 48));
            int rows = Math.min(total, Math.max(minimum, (total + columns - 1) / columns));
            int largestRow = (total + rows - 1) / rows;
            shortToolLabels = width / largestRow - 4 < 60;
            int height = rows == 1 ? 88 : rows == 2 ? 51 : 39;

            for (int rowIndex = 0; rowIndex < rows; rowIndex++) {
                LinearLayout row = new LinearLayout(getContext());
                LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(-1, height);
                if (rowIndex > 0) rowParams.topMargin = 4;
                temperatures.addView(row, rowParams);
                int remainingRows = rows - rowIndex;
                int rowSize = (total - temperatureTiles.size() + remainingRows - 1) / remainingRows;
                for (int column = 0; column < rowSize; column++) {
                    int index = temperatureTiles.size();
                    int tint = index < nozzleCount ? 0xffffbc8c : index == nozzleCount ? 0xffe6d58f : 0xffa4bdd1;
                    TemperatureTile tile = new TemperatureTile(tint,height,materialSize,swatchSize);
                    LinearLayout.LayoutParams tileParams = new LinearLayout.LayoutParams(0, -1, 1);
                    if (column > 0) tileParams.leftMargin = 4;
                    row.addView(tile, tileParams);
                    temperatureTiles.add(tile);
                }
            }
        }

        private void refreshTemperatures(JSONObject s, boolean live) {
            ArrayList<String[]> nozzles = new ArrayList<>();
            JSONArray readings = live ? s.optJSONArray("nozzle_readings") : null;
            JSONObject current = widgetSpecs.optJSONObject(spec.optString("_widgetId"));
            JSONObject preset = (current == null ? spec : current).optJSONObject("_presentation");
            JSONObject labels = preset == null ? null : preset.optJSONObject("labels");
            java.util.HashMap<Integer,JSONObject> metadata=new java.util.HashMap<>();
            java.util.TreeMap<Integer,String> tools = new java.util.TreeMap<>();
            for (int tool = 0; tool < 16; tool++) {
                if (labels != null && labels.has("nozzle." + tool)) tools.put(tool,"—");
            }
            if (readings != null) {
                for (int i = 0; i < Math.min(readings.length(), 16); i++) {
                    JSONObject nozzle = readings.optJSONObject(i);
                    if (nozzle != null && nozzle.has("tool")) {
                        metadata.put(nozzle.optInt("tool"),nozzle);
                        tools.put(nozzle.optInt("tool"), temperature(nozzle, "temperature"));
                    }
                }
            } else if (live) {
                // Older Studio versions send a formatted summary, including an extra Â before °.
                Matcher summary = TOOL_TEMPERATURE.matcher(s.optString("nozzles"));
                while (nozzles.size() < 2 && summary.find()) {
                    nozzles.add(new String[]{nozzleLabel(s,Integer.parseInt(summary.group(1).substring(1))), summary.group(2) + "°C"});
                }
            }
            for (java.util.Map.Entry<Integer,String> tool : tools.entrySet())
                nozzles.add(new String[]{nozzleLabel(s,tool.getKey()),tool.getValue(),String.valueOf(tool.getKey())});
            if (nozzles.isEmpty()) nozzles.add(new String[]{"NOZZLE", live ? temperature(s, "nozzle_temper") : "—"});

            layoutTemperatures(nozzles.size());
            for (int i = 0; i < nozzles.size(); i++) {
                String[] nozzle = nozzles.get(i);
                String title = shortToolLabels && nozzle[0].startsWith("NOZZLE T") ? nozzle[0].substring(7) : nozzle[0];
                TemperatureTile tile=temperatureTiles.get(i);
                tile.show(title,nozzle[1]);
                JSONObject info=nozzle.length>2 ? metadata.get(Integer.parseInt(nozzle[2])) : null;
                String material=info==null ? "" : info.optString("material");
                if (material.isEmpty() && labels!=null && info!=null)
                    material=labels.optString("filament."+info.optString("filamentProfile"));
                String color=info==null ? "" : info.optString("color");
                tile.showFilament(material,color.matches("#[0-9a-fA-F]{6}") ? color : "");
            }
            boolean grid=lastMinimumRows>1;
            boolean sideBoxes=sideColumn.getChildCount()>0;
            boolean visible=temperatures.getVisibility()==VISIBLE;
            sideColumn.setVisibility(visible && sideBoxes ? VISIBLE : GONE);
            environment.setVisibility(visible && grid && !sideBoxes ? VISIBLE : GONE);
            if(sideBoxes){
                for(int i=0;i<sideColumn.getChildCount();i++){
                    TemperatureTile tile=(TemperatureTile)sideColumn.getChildAt(i);
                    String key=(String)tile.getTag();
                    tile.show(labels==null ? key : labels.optString(key,key), live ? temperature(s,key) : "\u2014");
                }
                return;
            }
            if(grid){
                environment.setText("Bed "+(live ? temperature(s,"bed_temper") : "—")
                    +"    Chamber "+(live ? temperature(s,"chamber_temper") : "—"));
                return;
            }
            temperatureTiles.get(nozzles.size()).show("BED", live ? temperature(s, "bed_temper") : "—");
            temperatureTiles.get(nozzles.size() + 1).show("CHAMBER", live ? temperature(s, "chamber_temper") : "—");
        }
        private Button btn(String s,int color,Runnable action){Button b=new Button(getContext());b.setText(s);b.setTextColor(color);b.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX,13);b.setAllCaps(false);b.setMinHeight(0);b.setMinimumHeight(0);b.setPadding(8,0,8,0);GradientDrawable d=new GradientDrawable();d.setColor(0x18ffffff);d.setCornerRadius(14);d.setStroke(1,0x16ffffff);b.setBackground(d);b.setOnClickListener(v->action.run());return b;}
        private String nozzleLabel(JSONObject s,int tool){
            JSONObject currentSpec=widgetSpecs.optJSONObject(spec.optString("_widgetId"));
            return WidgetPresentation.label(currentSpec==null?spec:currentSpec,"nozzle."+tool,"NOZZLE T"+tool);
        }
        void refresh(){
            JSONObject s=snapshot(spec);
            JSONObject current=widgetSpecs.optJSONObject(spec.optString("_widgetId"));
            JSONObject scenes=(current==null?spec:current).optJSONObject("_scene");
            boolean stale=received==0 || SystemClock.elapsedRealtime()-received>=10000;
            packageFrame=scenes==null?null:scenes.optJSONObject(stale && scenes.has("expandedOffline")?"expandedOffline":"expanded");
            boolean packaged=packageFrame!=null;
            packageView.setVisibility(packaged?VISIBLE:GONE);
            ((View)name.getParent()).setVisibility(packaged?GONE:VISIBLE);
            ((View)temperatures.getParent()).setVisibility(packaged?GONE:VISIBLE);
            if(packaged){
                body.setPadding(0,6,0,4);
                packageView.invalidate();
            }else{
            name.setText(s.optString("name","Bambu Lab"));status.setText(fresh(s)?"●  "+state(s):"●  OFFLINE");status.setTextColor(fresh(s)?accent:muted);
            value.setText(metric(s,"progress"));job.setVisibility(spec.optBoolean("showJob",true)?VISIBLE:GONE);
            String filename=metric(s,"job");if(!filename.contentEquals(job.getText()))job.setText(filename);
            progress.setProgress(fresh(s)?Math.max(0,Math.min(100,s.optInt("mc_percent"))):0);
            String summary=spec.optBoolean("showRemaining",true)?metric(s,"remaining")+" left":"";
            if(spec.optBoolean("showLayers",true))summary+=(summary.isEmpty()?"":"  ·  ")+metric(s,"layers");details.setText(fresh(s)?summary:"Waiting for a live printer connection");
            temperatures.setVisibility(spec.optBoolean("showTemperatures",true)?VISIBLE:GONE);
            refreshTemperatures(s, fresh(s));
            }
            String action=s.optString("gcode_state").equals("PAUSE")?"resume":"pause";pause.setText(action.equals("resume")?"▶  Resume":"Ⅱ  Pause");
            boolean controls=spec.optBoolean("showControls",true)&&fresh(s);pause.setEnabled(controls&&s.optBoolean("can_"+action));stop.setEnabled(controls&&s.optBoolean("can_stop"));light.setEnabled(controls&&s.optBoolean("can_"+(s.optString("light").equals("on")?"light_off":"light_on")));
            String reason=s.optString("control_reason","");controlHint.setText(reason);controlHint.setVisibility("bambu".equals(spec.optString("kind"))&&spec.optBoolean("showControls",true)&&!reason.isEmpty()?VISIBLE:GONE);
            boolean show=spec.optBoolean("showControls",true)&&s.optBoolean("controls")&&fresh(s);
            pause.setVisibility(show&&s.optBoolean("print_controls_available")?VISIBLE:GONE);stop.setVisibility(pause.getVisibility());
            String lightState=s.optString("light");light.setVisibility(show&&(lightState.equals("on")||lightState.equals("off"))?VISIBLE:GONE);
            for(Button b:new Button[]{pause,stop,light})b.setAlpha(b.isEnabled()?1:.55f);
        }
        void open(){requestFocus();if(sourceItem!=null)sourceItem.setAlpha(0);animateTo(true);}
        void close(){if(closing)return;closing=true;animateTo(false);}
        private void animateTo(boolean opening){
            if(animator!=null)animator.cancel();float start=fraction;
            boolean motion=spec.optBoolean("liquidMotion",true)&&Settings.Global.getFloat(getContext().getContentResolver(),Settings.Global.ANIMATOR_DURATION_SCALE,1)>0;
            animator=ValueAnimator.ofFloat(0,1);animator.setInterpolator(new LinearInterpolator());animator.setDuration(motion?(opening?650:450):150);
            animator.addUpdateListener(a->{float t=(Float)a.getAnimatedValue();float eased=motion?LiquidGeometry.spring(t):t;fraction=opening?start+(1-start)*eased:start*(1-t)*(1-t);for(int i=0;i<neighbors.size();i++)neighbors.get(i).setTranslationX(translations.get(i)+movements.get(i)*fraction);body.setAlpha(Math.max(0,Math.min(1,(fraction-.18f)/.65f)));invalidate();});
            animator.addListener(new AnimatorListenerAdapter(){public void onAnimationEnd(Animator a){if(!opening){restore();host.removeView(WaterLayer.this);if(expanded==WaterLayer.this)expanded=null;source.requestFocus();}}});animator.start();
        }
        private void restore(){if(restored)return;restored=true;for(int i=0;i<neighbors.size();i++)neighbors.get(i).setTranslationX(translations.get(i));if(sourceItem!=null)sourceItem.setAlpha(sourceAlpha);}
        private void outline(){
            float f=fraction;current.set(from.left+(to.left-from.left)*f,from.top,from.right+(to.right-from.right)*f,from.bottom);
            float l=Math.max(0,current.left),r=Math.min(getWidth(),current.right),t=current.top,b=current.bottom;
            float wave=(float)(Math.sin(Math.max(0,Math.min(1,f))*Math.PI)*6);
            if(Math.abs(wave)<.01f){path.reset();path.addRoundRect(new RectF(l,t,r,b),radius,radius,Path.Direction.CW);return;}
            float k=radius*.55228475f;
            path.reset();path.moveTo(l+radius,t);path.cubicTo(l+current.width()*.35f,t-wave,l+current.width()*.65f,t+wave,r-radius,t);
            path.cubicTo(r-radius+k,t,r,t+radius-k,r,t+radius);path.lineTo(r,b-radius);path.cubicTo(r,b-radius+k,r-radius+k,b,r-radius,b);
            path.cubicTo(l+current.width()*.65f,b+wave,l+current.width()*.35f,b-wave,l+radius,b);path.cubicTo(l+radius-k,b,l,b-radius+k,l,b-radius);path.lineTo(l,t+radius);path.cubicTo(l,t+radius-k,l+radius-k,t,l+radius,t);path.close();
        }
        protected void onDraw(Canvas c){
            outline();
            int lifted=Color.rgb(Math.min(255,Color.red(background)+7),Math.min(255,Color.green(background)+10),Math.min(255,Color.blue(background)+12));
            paint.setColor(Color.WHITE);paint.setShader(new LinearGradient(current.left,current.top,current.right,current.bottom,new int[]{lifted,background},null,Shader.TileMode.CLAMP));paint.setStyle(Paint.Style.FILL);c.drawPath(path,paint);paint.setShader(null);
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(1.2f);paint.setColor(0x55c5e9ed);c.drawPath(path,paint);paint.setStyle(Paint.Style.FILL);
        }
        protected void dispatchDraw(Canvas c){outline();c.save();c.clipPath(path);super.dispatchDraw(c);c.restore();}
        private float touchX,touchY; private boolean swiping,inside;
        public boolean onTouchEvent(MotionEvent event){
            if(event.getActionMasked()==MotionEvent.ACTION_UP){
                if(swiping&&BambuPresentation.dismiss(event.getY()-touchY,from.height(),ViewConfiguration.get(getContext()).getScaledTouchSlop()))close();
                else if(!inside&&!current.contains(event.getX(),event.getY()))close();
                swiping=false;
            }else if(event.getActionMasked()==MotionEvent.ACTION_CANCEL)swiping=false;
            return true;
        }
        public boolean onInterceptTouchEvent(MotionEvent event){
            if(closing||(animator!=null&&animator.isRunning()))return true;
            if(event.getActionMasked()==MotionEvent.ACTION_DOWN){touchX=event.getX();touchY=event.getY();inside=current.contains(touchX,touchY);swiping=false;}
            else if(event.getActionMasked()==MotionEvent.ACTION_MOVE&&inside){
                float dy=event.getY()-touchY,dx=Math.abs(event.getX()-touchX);
                if(BambuPresentation.downward(dx,dy,ViewConfiguration.get(getContext()).getScaledTouchSlop())){swiping=true;getParent().requestDisallowInterceptTouchEvent(true);return true;}
            }
            return false;
        }
        protected void onDetachedFromWindow(){if(animator!=null)animator.cancel();restore();if(expanded==this)expanded=null;super.onDetachedFromWindow();}
    }
}
