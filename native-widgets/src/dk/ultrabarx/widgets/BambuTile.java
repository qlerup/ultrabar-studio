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
    private static volatile long received;
    private static WaterLayer expanded;
    private static final java.util.ArrayDeque<JSONObject> commands = new java.util.ArrayDeque<>();
    private static final int WHITE = 0xffeff6fa, MUTED = 0xff96aab5, MINT = 0xff86e4c3;
    private static final Pattern TOOL_TEMPERATURE = Pattern.compile("(T[0-9]+) ([0-9]+) / [0-9]+Â?°");
    public static void update(JSONObject data, long timestamp) {
        printers = data == null ? new JSONObject() : data; received = timestamp;
        main.post(() -> { if (expanded != null) expanded.refresh(); });
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
        label(canvas,p,value,22,108,primary.equals("progress")?52:30,text,true,!s.optString("model","generic").equals("generic")?width-90:width-40);
        String model=s.optString("model","generic");
        if(width>=180)PrinterPortrait.draw(canvas,model,width-72,62,54,accent);
        label(canvas,p,primary.equals("progress")?state(s):primary.equals("remaining")?"TIME REMAINING":primary.equals("temperature")?"ACTIVE NOZZLE":"PRINTER STATUS",23,133,11,accent,false,width-40);
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
        private final LinearLayout body, hero, temperatures, actions;
        private TextView name, status, value, job, details, controlHint;
        private final ArrayList<TemperatureTile> temperatureTiles = new ArrayList<>();
        private boolean shortToolLabels;
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
            if(row!=null){
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
            to.set(left,from.top,left+width,from.bottom);current.set(from);
            if(row!=null){for(int i=0;i<row.getChildCount();i++){View neighbor=row.getChildAt(i);if(neighbor==sourceItem)continue;int[] pos=new int[2];neighbor.getLocationOnScreen(pos);float x=pos[0]-base[0];float movement=x<from.left?to.left-from.left:to.right-from.right;neighbors.add(neighbor);translations.add(neighbor.getTranslationX());movements.add(movement);}}
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
            hero.addView(job);
            progress=new ProgressBar(getContext(),null,android.R.attr.progressBarStyleHorizontal);progress.setMax(100);progress.setProgressTintList(android.content.res.ColorStateList.valueOf(accent));LinearLayout.LayoutParams progressParams=new LinearLayout.LayoutParams(-1,4);progressParams.setMargins(0,8,18,6);hero.addView(progress,progressParams);
            details=txt("Waiting for printer",12,muted,false);hero.addView(details);
            middle.addView(hero,new LinearLayout.LayoutParams(0,-2,1.15f));
            temperatures=new LinearLayout(getContext());temperatures.setOrientation(LinearLayout.VERTICAL);temperatures.setPadding(12,0,0,0);
            middle.addView(temperatures,new LinearLayout.LayoutParams(0,-2,1));body.addView(middle,new LinearLayout.LayoutParams(-1,0,1));
            controlHint=txt("",11,muted,false);body.addView(controlHint);
            actions=new LinearLayout(getContext());
            pause=btn("Ⅱ  Pause",accent,()->execute(getContext(),spec,snapshot(spec).optString("gcode_state").equals("PAUSE")?"resume":"pause"));
            stop=btn("■  Stop",0xffffa6ab,()->new AlertDialog.Builder(getContext()).setTitle("Stop this print?").setMessage("The current print will end and cannot be resumed.").setNegativeButton("Keep printing",null).setPositiveButton("Stop print",(d,w)->execute(getContext(),spec,"stop")).show());
            light=btn("◉  Light",foreground,()->execute(getContext(),spec,snapshot(spec).optString("light").equals("on")?"light_off":"light_on"));
            for(Button button:new Button[]{pause,stop,light}){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,42,1);p.setMargins(0,0,6,0);actions.addView(button,p);}
            body.addView(actions);refresh();
            setOnKeyListener((v,key,event)->{if(key==KeyEvent.KEYCODE_BACK){if(event.getAction()==KeyEvent.ACTION_UP)close();return true;}return false;});
        }
        private TextView txt(String s,int size,int color,boolean bold){TextView v=new TextView(getContext());v.setText(s);v.setTextColor(color);v.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX,size);v.setSingleLine(true);v.setEllipsize(android.text.TextUtils.TruncateAt.END);if(bold)v.setTypeface(Typeface.create("sans-serif-medium",0));return v;}
        private final class TemperatureTile extends LinearLayout {
            final TextView label, reading;

            TemperatureTile(int tint, int rowHeight) {
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
                addView(label, new LinearLayout.LayoutParams(-1, 15));

                reading = txt("—", 26, foreground, true);
                reading.setHorizontallyScrolling(false);
                reading.setGravity(Gravity.CENTER);
                reading.setAutoSizeTextTypeUniformWithConfiguration(12, 26, 1, android.util.TypedValue.COMPLEX_UNIT_PX);
                addView(reading, new LinearLayout.LayoutParams(-1, Math.min(36, rowHeight - 15)));
            }

            void show(String title, String value) {
                if (!title.contentEquals(label.getText())) label.setText(title);
                if (!value.contentEquals(reading.getText())) reading.setText(value);
            }
        }

        private void layoutTemperatures(int nozzleCount) {
            int total = nozzleCount + 2;
            if (temperatureTiles.size() == total) return;
            temperatureTiles.clear();
            temperatures.removeAllViews();

            float weight = nozzleCount > 2 ? 2.5f : nozzleCount == 2 ? 1.45f : 1f;
            LinearLayout.LayoutParams params = (LinearLayout.LayoutParams) temperatures.getLayoutParams();
            params.weight = weight;
            temperatures.setLayoutParams(params);
            float width = (to.width() - body.getPaddingLeft() - body.getPaddingRight()) * weight / (1.15f + weight) - temperatures.getPaddingLeft();
            int columns = Math.max((total + 2) / 3, (int) (width / 48));
            int rows = (total + columns - 1) / columns;
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
                    TemperatureTile tile = new TemperatureTile(tint, height);
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
            if (readings != null) {
                for (int i = 0; i < Math.min(readings.length(), 16); i++) {
                    JSONObject nozzle = readings.optJSONObject(i);
                    if (nozzle != null && nozzle.has("tool")) {
                        nozzles.add(new String[]{nozzleLabel(s,nozzle.optInt("tool")), temperature(nozzle, "temperature")});
                    }
                }
            } else if (live) {
                // Older Studio versions send a formatted summary, including an extra Â before °.
                Matcher tools = TOOL_TEMPERATURE.matcher(s.optString("nozzles"));
                while (nozzles.size() < 2 && tools.find()) {
                    nozzles.add(new String[]{nozzleLabel(s,Integer.parseInt(tools.group(1).substring(1))), tools.group(2) + "°C"});
                }
            }
            if (nozzles.isEmpty()) nozzles.add(new String[]{"NOZZLE", live ? temperature(s, "nozzle_temper") : "—"});

            layoutTemperatures(nozzles.size());
            for (int i = 0; i < nozzles.size(); i++) {
                String[] nozzle = nozzles.get(i);
                String title = shortToolLabels && nozzle[0].startsWith("NOZZLE T") ? nozzle[0].substring(7) : nozzle[0];
                temperatureTiles.get(i).show(title, nozzle[1]);
            }
            temperatureTiles.get(nozzles.size()).show("BED", live ? temperature(s, "bed_temper") : "—");
            temperatureTiles.get(nozzles.size() + 1).show("CHAMBER", live ? temperature(s, "chamber_temper") : "—");
        }
        private Button btn(String s,int color,Runnable action){Button b=new Button(getContext());b.setText(s);b.setTextColor(color);b.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX,13);b.setAllCaps(false);b.setMinHeight(0);b.setMinimumHeight(0);b.setPadding(8,0,8,0);GradientDrawable d=new GradientDrawable();d.setColor(0x18ffffff);d.setCornerRadius(14);d.setStroke(1,0x16ffffff);b.setBackground(d);b.setOnClickListener(v->action.run());return b;}
        private String nozzleLabel(JSONObject s,int tool){
            return BambuPresentation.nozzleLabel(s.optString("model"),tool);
        }
        void refresh(){
            JSONObject s=snapshot(spec);name.setText(s.optString("name","Bambu Lab"));status.setText(fresh(s)?"●  "+state(s):"●  OFFLINE");status.setTextColor(fresh(s)?accent:muted);
            value.setText(metric(s,"progress"));job.setVisibility(spec.optBoolean("showJob",true)?VISIBLE:GONE);
            String filename=metric(s,"job");if(!filename.contentEquals(job.getText()))job.setText(filename);
            progress.setProgress(fresh(s)?Math.max(0,Math.min(100,s.optInt("mc_percent"))):0);
            String summary=spec.optBoolean("showRemaining",true)?metric(s,"remaining")+" left":"";
            if(spec.optBoolean("showLayers",true))summary+=(summary.isEmpty()?"":"  ·  ")+metric(s,"layers");details.setText(fresh(s)?summary:"Waiting for a live printer connection");
            temperatures.setVisibility(spec.optBoolean("showTemperatures",true)?VISIBLE:GONE);
            refreshTemperatures(s, fresh(s));
            String action=s.optString("gcode_state").equals("PAUSE")?"resume":"pause";pause.setText(action.equals("resume")?"▶  Resume":"Ⅱ  Pause");
            boolean controls=spec.optBoolean("showControls",true)&&fresh(s);pause.setEnabled(controls&&s.optBoolean("can_"+action));stop.setEnabled(controls&&s.optBoolean("can_stop"));light.setEnabled(controls&&s.optBoolean("can_"+(s.optString("light").equals("on")?"light_off":"light_on")));
            String reason=s.optString("control_reason","");controlHint.setText(reason);controlHint.setVisibility(spec.optBoolean("showControls",true)&&!reason.isEmpty()?VISIBLE:GONE);
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
