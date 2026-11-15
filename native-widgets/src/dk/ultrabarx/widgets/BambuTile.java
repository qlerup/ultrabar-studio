package dk.ultrabarx.widgets;

import android.animation.*;
import android.app.AlertDialog;
import android.content.*;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.view.animation.LinearInterpolator;
import android.widget.*;
import org.json.*;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.concurrent.Executors;

/** Model-independent Core home tile. Credential ownership remains in the companion APK. */
public final class BambuTile {
    private static final Uri URI = Uri.parse("content://dk.ultrabar.bambu.status");
    private static final Handler main = new Handler(Looper.getMainLooper());
    private static final java.util.concurrent.ExecutorService io = Executors.newSingleThreadExecutor(r -> { Thread t = new Thread(r, "BambuWidgetIPC"); t.setDaemon(true); return t; });
    private static final ArrayList<WeakReference<View>> views = new ArrayList<>();
    private static volatile JSONObject data = new JSONObject();
    private static volatile long received;
    private static boolean polling;
    private static final java.util.concurrent.atomic.AtomicBoolean reading = new java.util.concurrent.atomic.AtomicBoolean();
    private static WaterLayer expanded;
    private static final int WHITE = 0xffeff6fa, MUTED = 0xff96aab5, MINT = 0xff86e4c3;
    private static void track(View view) {
        boolean found = false;
        for (int i = views.size()-1; i >= 0; i--) { View v = views.get(i).get(); if (v == null) views.remove(i); else if (v == view) found = true; }
        if (!found) views.add(new WeakReference<>(view));
        if (polling) return; polling = true;
        main.post(new Runnable() { public void run() {
            View source = null;
            for (int i = views.size()-1; i >= 0; i--) { View v = views.get(i).get(); if (v == null) views.remove(i); else if (v.isAttachedToWindow() && v.isShown()) source = v; }
            if (source != null && reading.compareAndSet(false,true)) {
                Context context = source.getContext();
                io.execute(() -> {
                    JSONObject next;
                    try {
                        Bundle reply = context.getContentResolver().call(URI, "snapshot", null, null);
                        String json = reply == null ? "{}" : reply.getString("json", "{}");
                        next = json.length() <= 32768 ? new JSONObject(json) : new JSONObject();
                    } catch (Exception e) { next = new JSONObject(); }
                    data = next; received = SystemClock.elapsedRealtime();
                    reading.set(false);
                    main.post(() -> {
                        for (WeakReference<View> ref : views) { View v = ref.get(); if (v != null) v.invalidate(); }
                        if (expanded != null) expanded.refresh();
                    });
                });
            }
            main.postDelayed(this, 1000);
        }});
    }
    private static boolean fresh(JSONObject s) { return received > 0 && SystemClock.elapsedRealtime()-received < 4000 && s.optBoolean("fresh"); }
    private static String state(JSONObject s) {
        if (!fresh(s)) return s.has("connection") ? "Offline" : "Set up printer";
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
            case "temperature": return s.has("nozzle_temper") ? s.optInt("nozzle_temper")+"°" : "—";
            case "job": return s.optString("subtask_name", "No active job");
            case "layers": return s.has("layer_num") ? "Layer "+s.optInt("layer_num")+" / "+s.optInt("total_layer_num") : "Layer —";
            case "none": return ""; default: return "—";
        }
    }
    private static void label(Canvas canvas, Paint paint, String text, float x, float y, float size, int color, boolean bold, float maxWidth) {
        paint.setColor(color); paint.setTextSize(size); paint.setTypeface(Typeface.create(bold?"sans-serif-medium":"sans-serif",Typeface.NORMAL));
        while (paint.measureText(text) > maxWidth && text.length() > 2) text = text.substring(0,text.length()-2)+"…";
        canvas.drawText(text, x, y, paint);
    }
    private static void printerMark(Canvas c,Paint p,float x,float y,float scale,int accent){
        c.save();c.translate(x,y);c.scale(scale,scale);p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(1.6f);p.setColor((accent&0x00ffffff)|0x99000000);
        c.drawRoundRect(0,0,43,56,4,4,p);c.drawLine(4,12,39,12,p);c.drawLine(22,12,22,22,p);c.drawLine(16,22,28,22,p);c.drawLine(28,22,22,29,p);c.drawLine(22,29,16,22,p);
        c.drawLine(7,47,36,47,p);c.drawLine(11,43,22,36,p);c.drawLine(22,36,33,43,p);c.drawLine(33,43,22,50,p);c.drawLine(22,50,11,43,p);p.setStyle(Paint.Style.FILL);c.restore();
    }
    public static void draw(View source, Canvas canvas, float width, JSONObject spec, String title) {
        track(source); Paint p = new Paint(3); JSONObject s = data;
        int background = Color.parseColor(spec.optString("background", "#14202b"));
        int accent = Color.parseColor(spec.optString("accent", "#86e4c3"));
        int text = Color.parseColor(spec.optString("textColor", "#eff6fa"));
        RectF box = new RectF(1,1,width-1,239);
        p.setShader(new LinearGradient(0,0,width,240,new int[]{background,Color.rgb(Color.red(background)+Math.min(4,255-Color.red(background)), Color.green(background)+Math.min(5,255-Color.green(background)), Color.blue(background)+Math.min(8,255-Color.blue(background)))},null,Shader.TileMode.CLAMP));
        canvas.drawRoundRect(box,24,24,p); p.setShader(null);
        p.setStyle(Paint.Style.STROKE); p.setStrokeWidth(1); p.setColor(0x26ffffff); canvas.drawRoundRect(box,24,24,p); p.setStyle(Paint.Style.FILL);
        p.setColor(fresh(s)?accent:0xff74838b); canvas.drawCircle(24,28,3,p);
        label(canvas,p,s.optString("name",title==null?"Bambu Lab":title),34,33,14,text,true,width-62);
        String primary = spec.optString("primary","progress"), value = metric(s,primary);
        label(canvas,p,value,22,108,primary.equals("progress")?52:30,text,true,width-40);
        if(primary.equals("progress")&&width>=245)printerMark(canvas,p,width-72,65,.95f,accent);
        label(canvas,p,primary.equals("progress")?state(s):primary.equals("remaining")?"TIME REMAINING":primary.equals("temperature")?"ACTIVE NOZZLE":"PRINTER STATUS",23,133,11,accent,false,width-40);
        label(canvas,p,metric(s,spec.optString("secondary","remaining")),23,165,14,MUTED,false,width-42);
        p.setColor(0x22ffffff); canvas.drawRoundRect(22,183,width-22,187,2,2,p);
        float percent = fresh(s)?Math.max(0,Math.min(100,s.optInt("mc_percent"))):0;
        p.setColor(accent); canvas.drawRoundRect(22,183,22+(width-44)*percent/100,187,2,2,p);
        label(canvas,p,"Tap to unfold",23,218,11,MUTED,false,width-64);
        label(canvas,p,"↗",width-40,219,18,accent,false,24);
    }
    private static void execute(Context context, String action) {
        io.execute(() -> {
            boolean accepted = false;
            try { Bundle reply = context.getContentResolver().call(URI,action,null,null); accepted=reply!=null && reply.getBoolean("accepted"); } catch(Exception ignored) {}
            final boolean ok = accepted;
            main.post(() -> Toast.makeText(context,ok?"Request sent; waiting for printer":"Unavailable. Check printer status and enable controls in Bambu Panel.",Toast.LENGTH_LONG).show());
        });
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
        private TextView name, status, value, job, details, nozzle, bed, chamber;
        private Button pause, stop, light;
        private ProgressBar progress;
        private ValueAnimator animator;
        private float fraction; private boolean closing;
        WaterLayer(View source, ViewGroup host, JSONObject spec) {
            super(source.getContext()); this.source=source;this.host=host;this.spec=spec;
            foreground=Color.parseColor(spec.optString("textColor","#eff6fa"));accent=Color.parseColor(spec.optString("accent","#86e4c3"));background=Color.parseColor(spec.optString("background","#14202b"));
            muted=Color.rgb((int)(Color.red(foreground)*.62f+Color.red(background)*.38f),(int)(Color.green(foreground)*.62f+Color.green(background)*.38f),(int)(Color.blue(foreground)*.62f+Color.blue(background)*.38f));
            setWillNotDraw(false);setFocusableInTouchMode(true);setContentDescription("Expanded Bambu printer controls");requestFocus();
            int[] origin=new int[2],base=new int[2];source.getLocationOnScreen(origin);host.getLocationOnScreen(base);
            from.set(origin[0]-base[0],origin[1]-base[1],origin[0]-base[0]+source.getWidth(),origin[1]-base[1]+source.getHeight());
            float viewportLeft=8,viewportWidth=host.getWidth()-16;
            ViewParent ancestor=source.getParent();
            while(ancestor instanceof View){View v=(View)ancestor;if(v.getClass().getName().contains("RecyclerView")){int[] pos=new int[2];v.getLocationOnScreen(pos);viewportLeft=pos[0]-base[0]+4;viewportWidth=v.getWidth()-8;break;}ancestor=v.getParent();}
            float width=LiquidGeometry.width(from.width(),viewportWidth,spec.optInt("expandedSlots",3));
            float left=LiquidGeometry.left(from.left,width,viewportLeft,viewportWidth);
            to.set(left,from.top,left+width,from.bottom);current.set(from);
            body=new LinearLayout(getContext());body.setOrientation(LinearLayout.VERTICAL);body.setPadding(18,12,18,12);
            FrameLayout.LayoutParams bp=new FrameLayout.LayoutParams((int)to.width(),(int)to.height());bp.leftMargin=(int)to.left;bp.topMargin=(int)to.top;addView(body,bp);
            LinearLayout header=new LinearLayout(getContext());header.setGravity(Gravity.CENTER_VERTICAL);
            name=txt("Bambu Lab",16,foreground,true);header.addView(name,new LinearLayout.LayoutParams(0,32,1));
            status=txt("LOCAL",11,accent,false);header.addView(status);
            header.addView(btn("×",muted,this::close),new LinearLayout.LayoutParams(40,32));body.addView(header);
            LinearLayout middle=new LinearLayout(getContext());middle.setGravity(Gravity.CENTER_VERTICAL);
            hero=new LinearLayout(getContext());hero.setOrientation(LinearLayout.VERTICAL);
            LinearLayout headline=new LinearLayout(getContext());headline.setGravity(Gravity.CENTER_VERTICAL);
            value=txt("—",42,foreground,true);headline.addView(value,new LinearLayout.LayoutParams(0,-2,1));
            View mark=new View(getContext()){protected void onDraw(Canvas c){printerMark(c,new Paint(3),2,2,.85f,accent);}};headline.addView(mark,new LinearLayout.LayoutParams(54,54));hero.addView(headline);
            job=txt("No active print",13,foreground,false);hero.addView(job);
            progress=new ProgressBar(getContext(),null,android.R.attr.progressBarStyleHorizontal);progress.setMax(100);progress.setProgressTintList(android.content.res.ColorStateList.valueOf(accent));LinearLayout.LayoutParams progressParams=new LinearLayout.LayoutParams(-1,4);progressParams.setMargins(0,8,18,6);hero.addView(progress,progressParams);
            details=txt("Waiting for printer",12,muted,false);hero.addView(details);
            middle.addView(hero,new LinearLayout.LayoutParams(0,-2,1.15f));
            temperatures=new LinearLayout(getContext());temperatures.setPadding(18,0,0,0);
            nozzle=temperatureTile("NOZZLE",0xffffbc8c);bed=temperatureTile("BED",0xffe6d58f);chamber=temperatureTile("CHAMBER",0xffa4bdd1);
            middle.addView(temperatures,new LinearLayout.LayoutParams(0,-2,1));body.addView(middle,new LinearLayout.LayoutParams(-1,0,1));
            actions=new LinearLayout(getContext());
            pause=btn("Ⅱ  Pause",accent,()->execute(getContext(),data.optString("gcode_state").equals("PAUSE")?"resume":"pause"));
            stop=btn("■  Stop",0xffffa6ab,()->new AlertDialog.Builder(getContext()).setTitle("Stop this print?").setMessage("The current print will end and cannot be resumed.").setNegativeButton("Keep printing",null).setPositiveButton("Stop print",(d,w)->execute(getContext(),"stop")).show());
            light=btn("◉  Light",foreground,()->execute(getContext(),data.optString("light").equals("on")?"light_off":"light_on"));
            for(Button button:new Button[]{pause,stop,light}){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,42,1);p.setMargins(0,0,6,0);actions.addView(button,p);}
            Button setup=btn("Setup ↗",muted,()->{try{Intent i=new Intent();i.setClassName("dk.ultrabar.bambu","dk.ultrabar.bambu.MainActivity");getContext().startActivity(i);close();}catch(Exception e){Toast.makeText(getContext(),"Install Bambu Panel from Store first",Toast.LENGTH_LONG).show();}});
            actions.addView(setup,new LinearLayout.LayoutParams(96,42));body.addView(actions);refresh();
            setOnKeyListener((v,key,event)->{if(key==KeyEvent.KEYCODE_BACK){if(event.getAction()==KeyEvent.ACTION_UP)close();return true;}return false;});
        }
        private TextView txt(String s,int size,int color,boolean bold){TextView v=new TextView(getContext());v.setText(s);v.setTextColor(color);v.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX,size);v.setSingleLine(true);v.setEllipsize(android.text.TextUtils.TruncateAt.END);if(bold)v.setTypeface(Typeface.create("sans-serif-medium",0));return v;}
        private TextView temperatureTile(String title,int tint){LinearLayout tile=new LinearLayout(getContext());tile.setOrientation(1);tile.setGravity(Gravity.CENTER_VERTICAL);tile.setPadding(12,10,8,10);GradientDrawable bg=new GradientDrawable();bg.setColor(0x0bffffff);bg.setCornerRadius(18);bg.setStroke(1,0x10ffffff);tile.setBackground(bg);tile.addView(txt(title,9,tint,false));TextView reading=txt("—",to.width()<650?20:26,foreground,true);reading.setPadding(0,5,0,0);tile.addView(reading);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,88,1);p.setMargins(0,0,6,0);temperatures.addView(tile,p);return reading;}
        private Button btn(String s,int color,Runnable action){Button b=new Button(getContext());b.setText(s);b.setTextColor(color);b.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX,13);b.setAllCaps(false);b.setMinHeight(0);b.setMinimumHeight(0);b.setPadding(8,0,8,0);GradientDrawable d=new GradientDrawable();d.setColor(0x18ffffff);d.setCornerRadius(14);d.setStroke(1,0x16ffffff);b.setBackground(d);b.setOnClickListener(v->action.run());return b;}
        void refresh(){
            JSONObject s=data;name.setText(s.optString("name","Bambu Lab"));status.setText(fresh(s)?"●  "+state(s):"●  OFFLINE");status.setTextColor(fresh(s)?accent:muted);
            value.setText(metric(s,"progress"));job.setVisibility(spec.optBoolean("showJob",true)?VISIBLE:GONE);job.setText(metric(s,"job"));
            progress.setProgress(fresh(s)?Math.max(0,Math.min(100,s.optInt("mc_percent"))):0);
            String summary=spec.optBoolean("showRemaining",true)?metric(s,"remaining")+" left":"";
            if(spec.optBoolean("showLayers",true))summary+=(summary.isEmpty()?"":"  ·  ")+metric(s,"layers");details.setText(fresh(s)?summary:"Waiting for a live printer connection");
            temperatures.setVisibility(spec.optBoolean("showTemperatures",true)?VISIBLE:GONE);
            String multi=s.optString("nozzles","");boolean multiple=fresh(s)&&!multi.isEmpty()&&!multi.equals("null");nozzle.setText(multiple?multi.replaceAll(" / [0-9]+°","°").replace("  ·  ","\n"):fresh(s)?s.optString("nozzle_temper","—")+"°":"—");nozzle.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX,multiple?13:to.width()<650?20:26);nozzle.setSingleLine(!multiple);nozzle.setMaxLines(multiple?2:1);
            bed.setText(fresh(s)?s.optString("bed_temper","—")+"°":"—");chamber.setText(fresh(s)&&s.has("chamber_temper")?s.optString("chamber_temper")+"°":"—");
            String action=s.optString("gcode_state").equals("PAUSE")?"resume":"pause";pause.setText(action.equals("resume")?"▶  Resume":"Ⅱ  Pause");
            boolean controls=spec.optBoolean("showControls",true)&&fresh(s);pause.setEnabled(controls&&s.optBoolean("can_"+action));stop.setEnabled(controls&&s.optBoolean("can_stop"));light.setEnabled(controls&&s.optBoolean("can_light_on"));
            for(Button b:new Button[]{pause,stop,light}){b.setVisibility(spec.optBoolean("showControls",true)?VISIBLE:GONE);b.setAlpha(b.isEnabled()?1:.55f);}
        }
        void open(){requestFocus();animateTo(true);}
        void close(){if(closing)return;closing=true;animateTo(false);}
        private void animateTo(boolean opening){
            if(animator!=null)animator.cancel();float start=fraction;
            boolean motion=spec.optBoolean("liquidMotion",true)&&Settings.Global.getFloat(getContext().getContentResolver(),Settings.Global.ANIMATOR_DURATION_SCALE,1)>0;
            animator=ValueAnimator.ofFloat(0,1);animator.setInterpolator(new LinearInterpolator());animator.setDuration(motion?(opening?650:450):150);
            animator.addUpdateListener(a->{float t=(Float)a.getAnimatedValue();float eased=motion?LiquidGeometry.spring(t):t;fraction=opening?start+(1-start)*eased:start*(1-t)*(1-t);body.setAlpha(Math.max(0,Math.min(1,(fraction-.18f)/.65f)));invalidate();});
            animator.addListener(new AnimatorListenerAdapter(){public void onAnimationEnd(Animator a){if(!opening){host.removeView(WaterLayer.this);if(expanded==WaterLayer.this)expanded=null;source.requestFocus();}}});animator.start();
        }
        private void outline(){
            float f=fraction;current.set(from.left+(to.left-from.left)*f,from.top,from.right+(to.right-from.right)*f,from.bottom);
            float l=Math.max(2,current.left),r=Math.min(getWidth()-2,current.right),t=current.top,b=current.bottom,radius=26;
            float wave=(float)(Math.sin(Math.max(0,Math.min(1,f))*Math.PI)*6);
            path.reset();path.moveTo(l+radius,t);path.cubicTo(l+current.width()*.35f,t-wave,l+current.width()*.65f,t+wave,r-radius,t);
            path.cubicTo(r,t,r,t,r,t+radius);path.lineTo(r,b-radius);path.cubicTo(r,b,r,b,r-radius,b);
            path.cubicTo(l+current.width()*.65f,b+wave,l+current.width()*.35f,b-wave,l+radius,b);path.cubicTo(l,b,l,b,l,b-radius);path.lineTo(l,t+radius);path.cubicTo(l,t,l,t,l+radius,t);path.close();
        }
        protected void onDraw(Canvas c){
            paint.setColor(Color.argb((int)(Math.min(1,fraction)*75),0,5,10));c.drawRect(0,0,getWidth(),getHeight(),paint);outline();
            int lifted=Color.rgb(Math.min(255,Color.red(background)+7),Math.min(255,Color.green(background)+10),Math.min(255,Color.blue(background)+12));
            paint.setColor(Color.WHITE);paint.setShader(new LinearGradient(current.left,current.top,current.right,current.bottom,new int[]{lifted,background},null,Shader.TileMode.CLAMP));paint.setStyle(Paint.Style.FILL);c.drawPath(path,paint);paint.setShader(null);
            paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(1.2f);paint.setColor(0x55c5e9ed);c.drawPath(path,paint);paint.setStyle(Paint.Style.FILL);
        }
        protected void dispatchDraw(Canvas c){outline();c.save();c.clipPath(path);super.dispatchDraw(c);c.restore();}
        public boolean onTouchEvent(android.view.MotionEvent event){if(event.getAction()==MotionEvent.ACTION_UP&&!current.contains(event.getX(),event.getY()))close();return true;}
        public boolean onInterceptTouchEvent(android.view.MotionEvent event){return closing||(animator!=null&&animator.isRunning());}
        protected void onDetachedFromWindow(){if(animator!=null)animator.cancel();if(expanded==this)expanded=null;super.onDetachedFromWindow();}
    }
}
