package dk.ultrabarx.widgets;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Outline;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewOutlineProvider;
import android.view.MotionEvent;
import android.widget.FrameLayout;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.lang.ref.WeakReference;
import java.util.ArrayList;

/** A real child view of LineOS's scrolling card, never a separate window. */
public final class StudioCard extends View {
    private static final String TAG = "ultrabar-studio-native-v1";
    private static final ViewOutlineProvider SMALL_OUTLINE = new ViewOutlineProvider() {
        @Override public void getOutline(View view, Outline outline) {
            outline.setRoundRect(0, 0, view.getWidth(), view.getHeight(), Math.min(view.getWidth(), view.getHeight()) / 4f);
        }
    };
    private static final ArrayList<WeakReference<StudioCard>> views = new ArrayList<>();
    private static volatile JSONObject state = new JSONObject();
    private static volatile long received = 0;
    private static final Handler main = new Handler(Looper.getMainLooper());
    private static boolean started = false;
    private final Paint paint = new Paint(3);
    private final SplitFlap splitFlap = new SplitFlap();
    private String widgetId, title;
    private JSONObject bambuSpec;
    private ViewOutlineProvider fullOutline;
    private final ArrayList<View> originals = new ArrayList<>();
    private final ArrayList<Integer> visibility = new ArrayList<>();

    public StudioCard(Context context) { super(context); setTag(TAG); setClickable(false); }

    public static void bind(View root, String id, String name) {
        int cardId = root.getResources().getIdentifier("card", "id", "com.ultrabar.launch");
        View candidate = root.findViewById(cardId);
        if (!(candidate instanceof FrameLayout)) return;
        FrameLayout card = (FrameLayout)candidate;
        StudioCard custom = (StudioCard)card.findViewWithTag(TAG);
        if (!id.startsWith("studio_native_")) {
            if (custom != null) {
                for (int i=0;i<custom.originals.size();i++) custom.originals.get(i).setVisibility(custom.visibility.get(i));
                card.removeView(custom);
            }
            return;
        }
        if (custom == null) {
            custom = new StudioCard(root.getContext());
            for (int i=0;i<card.getChildCount();i++) {
                View child=card.getChildAt(i);custom.originals.add(child);custom.visibility.add(child.getVisibility());child.setVisibility(GONE);
            }
            card.addView(custom,new FrameLayout.LayoutParams(-1,-1));
            views.add(new WeakReference<>(custom));
        }
        custom.widgetId=id;custom.title=name;custom.setContentDescription(name+" Studio widget");custom.invalidate();
        startReader();
    }

    private static synchronized void startReader() {
        if(started)return;started=true;
        Thread reader=new Thread(() -> {
            String previous="";
            while(true){
                try {
                    File file=new File("/data/local/tmp/ultrabar-studio-metrics.json");
                    if(file.length()>0 && file.length()<4194304){
                        String text=new String(Files.readAllBytes(file.toPath()),StandardCharsets.UTF_8);
                        if(!text.equals(previous)){JSONObject next=new JSONObject(text);state=next;BambuTile.updateSpecs(next.optJSONObject("widgets"));BambuTile.updateArtwork(next.optJSONObject("printerImages"));BambuTile.updateSceneImages(next.optJSONObject("sceneImages"));previous=text;received=Math.abs(System.currentTimeMillis()-file.lastModified())<10000?SystemClock.elapsedRealtime():0;BambuTile.update(next.optJSONObject("printers"),received);}
                    }
                } catch(Exception ignored) { /* Last sample expires visibly below. */ }
                BambuTile.update(state.optJSONObject("printers"),received);
                main.post(() -> {for(int i=views.size()-1;i>=0;i--){StudioCard v=views.get(i).get();if(v==null)views.remove(i);else v.invalidate();}});
                try{Thread.sleep(1000);}catch(InterruptedException e){return;}
            }
        },"StudioWidgetData");reader.setDaemon(true);reader.start();
    }

    private void text(Canvas c,String s,float x,float y,float size,int color,boolean bold){
        paint.setColor(color);paint.setTextSize(size);
        paint.setTypeface(Typeface.create(bold?"sans-serif-medium":"sans-serif",Typeface.NORMAL));
        c.drawText(s,x,y,paint);
    }
    private void bar(Canvas c,float y,float width,double value,int accent){
        paint.setColor(Color.rgb(49,64,60));c.drawRoundRect(22,y,width-22,y+6,3,3,paint);
        paint.setColor(accent);c.drawRoundRect(22,y,22+(width-44)*(float)Math.max(0,Math.min(100,value))/100,y+6,3,3,paint);
    }
    private static String gb(double n){return String.format(java.util.Locale.US,"%.1f",n);}
    private static int blend(int foreground,int background,float amount){return Color.rgb((int)(Color.red(foreground)*amount+Color.red(background)*(1-amount)),(int)(Color.green(foreground)*amount+Color.green(background)*(1-amount)),(int)(Color.blue(foreground)*amount+Color.blue(background)*(1-amount)));}
    private void drawSmall(Canvas canvas, JSONObject spec) {
        int width = getWidth(), height = getHeight();
        int foreground = Color.parseColor(spec.optString("textColor", "#eef6f2"));
        int accent = Color.parseColor(spec.optString("accent", "#94d9bb"));
        paint.setColor(Color.parseColor(spec.optString("background", "#192325")));
        canvas.drawRect(0, 0, width, height, paint);
        String label = WidgetPresentation.label(spec, "title", title == null ? "Studio" : title);
        String kind = spec.optString("kind"), reading = "—", detail = "";
        double percent = Double.NaN;
        boolean online = received > 0 && SystemClock.elapsedRealtime() - received < 10000;
        JSONObject metrics = state.optJSONObject("metrics");
        if (kind.equals("bambu")) {
            label = BambuTile.smallTitle(spec, label);
            reading = BambuTile.smallReading(spec);
            percent = BambuTile.smallProgress(spec);
        } else if (kind.equals("clock")) {
            java.util.Date now = new java.util.Date();
            boolean twelve = spec.optString("hourFormat", "24").equals("12");
            reading = new java.text.SimpleDateFormat(twelve ? "h:mm a" : "HH:mm", java.util.Locale.getDefault()).format(now);
            if (spec.optBoolean("showDate", true))
                detail = new java.text.SimpleDateFormat("d MMM", java.util.Locale.getDefault()).format(now);
        } else if (online && metrics != null) {
            if (kind.equals("disk")) {
                JSONArray disks = metrics.optJSONArray("disks"), drives = spec.optJSONArray("drives");
                String drive = spec.optString("drive", "all");
                if (drives != null && drives.length() > 0)
                    drive = drives.optString((int) ((SystemClock.elapsedRealtime() / 5000) % drives.length()));
                if (disks != null) for (int i = 0; i < disks.length(); i++) {
                    JSONObject disk = disks.optJSONObject(i);
                    if (disk != null && (drive.equals("all") || drive.equals(disk.optString("name")))) {
                        percent = disk.optDouble("percent");
                        detail = disk.optString("name").replace("\\", "");
                        break;
                    }
                }
            } else if (kind.equals("gpu")) {
                JSONObject gpu = metrics.optJSONObject("gpu");
                if (gpu != null) percent = gpu.optDouble("usage");
            } else percent = metrics.optDouble(kind);
            if (kind.equals("cpu") || kind.equals("gpu") || kind.equals("memory"))
                detail = kind.equals("memory") ? "RAM" : kind.toUpperCase(java.util.Locale.ROOT);
            if (!Double.isNaN(percent)) reading = Math.round(percent) + "%";
        }
        smallText(canvas, label, width, height * .28f, 13, foreground, true);
        smallText(canvas, reading, width, height * .61f, 23, foreground, true);
        if (!detail.isEmpty()) smallText(canvas, detail, width, height * .8f, 11, accent, false);
        if (!Double.isNaN(percent)) bar(canvas, height * .85f, width, percent, accent);
    }
    private void smallText(Canvas canvas, String value, int width, float baseline, float size, int color, boolean bold) {
        paint.setTextSize(size);
        paint.setTypeface(Typeface.create(bold ? "sans-serif-medium" : "sans-serif", Typeface.NORMAL));
        String fitted = android.text.TextUtils.ellipsize(value, new android.text.TextPaint(paint), width - 20,
                android.text.TextUtils.TruncateAt.END).toString();
        text(canvas, fitted, (width - paint.measureText(fitted)) / 2, baseline, size, color, bold);
    }
    @Override protected void onDraw(Canvas original){
        super.onDraw(original);Canvas c=original;float scale=getHeight()/240f;if(scale<=0)return;
        int white=Color.rgb(239,246,242),muted=Color.rgb(155,177,165),accent=Color.rgb(148,217,187);
        JSONObject specs=state.optJSONObject("widgets"),spec=specs==null?null:specs.optJSONObject(widgetId);
        JSONObject frames=spec==null?null:spec.optJSONObject("_scene");
        bambuSpec=spec!=null&&("bambu".equals(spec.optString("kind")) || frames!=null && frames.has("expanded"))?spec:null;
        if(bambuSpec!=null)try{bambuSpec.put("_widgetId",widgetId);}catch(Exception ignored){}
        setClickable(bambuSpec != null);
        boolean small = getHeight() < 160;
        if (getParent() instanceof View) {
            View parent = (View) getParent();
            if (small && parent.getOutlineProvider() != SMALL_OUTLINE) {
                fullOutline = parent.getOutlineProvider();
                parent.setOutlineProvider(SMALL_OUTLINE);
            } else if (!small && parent.getOutlineProvider() == SMALL_OUTLINE) {
                parent.setOutlineProvider(fullOutline);
            }
        }
        JSONObject scene = spec == null ? null : spec.optJSONObject("_scene");
        if (scene != null) {
            String size = small ? "small" : "large";
            boolean stale = received == 0 || SystemClock.elapsedRealtime()-received >= 10000;
            String frame = stale && scene.has(size+"Offline") ? size+"Offline" : size;
            if (PackageScene.draw(this, c, scene.optJSONObject(frame), state.optJSONObject("sceneImages"))) return;
        }
        JSONObject presentation = spec == null ? null : spec.optJSONObject("_presentation");
        JSONObject face = presentation == null ? null : presentation.optJSONObject("splitFlap");
        if (face != null && "clock".equals(spec.optString("kind"))) {
            splitFlap.draw(this, c, spec, face, title == null ? "Clock" : title, small);
            return;
        }
        if(spec != null && small) { drawSmall(c, spec); return; }
        c.save();c.scale(scale,scale);float width=getWidth()/scale;
        if(bambuSpec!=null){BambuTile.draw(this,c,width,spec,title);c.restore();return;}
        int background=Color.rgb(25,35,37);
        if(spec!=null)try{background=Color.parseColor(spec.optString("background","#192325"));}catch(Exception ignored){}
        if(spec!=null)try{white=Color.parseColor(spec.optString("textColor","#eef6f2"));}catch(Exception ignored){}
        muted=blend(white,background,.62f);
        paint.setColor(background);c.drawRoundRect(0,0,width,240,16,16,paint);
        if(spec!=null)try{accent=Color.parseColor(spec.optString("accent","#94d9bb"));}catch(Exception ignored){}
        String label=WidgetPresentation.label(spec,"title",title==null?"Studio":title);
        text(c,label.length()>26?label.substring(0,25)+"…":label,22,34,15,white,true);
        WidgetPresentation.draw(c,spec,width-62,40,40,accent);
        boolean online=received>0 && SystemClock.elapsedRealtime()-received<10000;
        JSONObject metrics=state.optJSONObject("metrics");
        if(spec!=null && spec.optString("kind").equals("clock")){
            java.util.Date now=new java.util.Date();
            String format=spec.optString("hourFormat","24").equals("12")?"hh:mm":"HH:mm";
            if(spec.optBoolean("showSeconds",true))format+=":ss";
            if(spec.optString("hourFormat","24").equals("12"))format+=" a";
            text(c,new java.text.SimpleDateFormat(format,java.util.Locale.getDefault()).format(now),22,116,32,white,true);
            if(spec.optBoolean("showDate",true)){
                String date=new java.text.SimpleDateFormat("EEE, d MMM yyyy",java.util.Locale.getDefault()).format(now);
                text(c,date,22,158,14,accent,false);
            }
            c.restore();return;
        }
        if(spec==null||metrics==null||!online){text(c,online?"Choose in Studio":"PC offline",22,118,25,muted,false);text(c,"Open Studio to reconnect",22,202,12,muted,false);c.restore();return;}
        String kind=spec.optString("kind");
        if(kind.equals("disk")){
            JSONArray drives=metrics.optJSONArray("disks"),pair=spec.optJSONArray("drives");String drive=spec.optString("drive","all");ArrayList<JSONObject> selected=new ArrayList<>();
            if(drives!=null)for(int i=0;i<drives.length();i++){JSONObject d=drives.optJSONObject(i);if(d==null)continue;boolean include=drive.equals(d.optString("name"));if(drive.equals("all")){include=pair==null; if(pair!=null)for(int j=0;j<pair.length();j++)if(pair.optString(j).equals(d.optString("name")))include=true;}if(include)selected.add(d);}
            if(selected.isEmpty()){text(c,"Drive unavailable",22,122,21,muted,false);c.restore();return;}
            if(drive.equals("all")){
                // Legacy ungrouped cards rotate pairs; Studio creates explicit pairs.
                int pages=(selected.size()+1)/2,start=DrivePage.start(selected.size(),SystemClock.elapsedRealtime()),page=start/2;
                for(int i=start;i<Math.min(start+2,selected.size());i++){
                    JSONObject d=selected.get(i);float y=78+(i-start)*77;String dn=d.optString("name").replace("\\","");
                    text(c,dn,22,y,19,white,true);text(c,gb(d.optDouble("percent"))+"%",width-83,y,19,white,false);
                    bar(c,y+13,width,d.optDouble("percent"),accent);text(c,gb(d.optDouble("used_gb"))+" / "+gb(d.optDouble("total_gb"))+" GB",22,y+35,12,muted,false);
                }
                if(pages>1)text(c,(page+1)+" / "+pages,width-48,229,10,muted,false);
            }else{
                JSONObject d=selected.get(0);text(c,d.optString("name").replace("\\","")+"  /  LOCAL DISK",22,63,11,accent,true);
                text(c,gb(d.optDouble("percent"))+"%",22,127,54,white,true);
                text(c,gb(d.optDouble("used_gb"))+" / "+gb(d.optDouble("total_gb"))+" GB",22,157,13,muted,false);
                bar(c,180,width,d.optDouble("percent"),accent);text(c,gb(d.optDouble("total_gb")-d.optDouble("used_gb"))+" GB free",22,219,12,muted,false);
            }
        }else{
            double value=metrics.optDouble(kind,Double.NaN);String detail="PC usage";
            if(kind.equals("gpu")){JSONObject gpu=metrics.optJSONObject("gpu");value=gpu==null?Double.NaN:gpu.optDouble("usage",Double.NaN);detail=gpu==null?"Sensor unavailable":gpu.optString("name");}
            if(kind.equals("memory"))detail=gb(metrics.optDouble("memory_used_gb"))+" / "+gb(metrics.optDouble("memory_total_gb"))+" GB";
            text(c,Double.isNaN(value)?"--":gb(value)+"%",22,116,49,white,true);
            text(c,detail.length()>30?detail.substring(0,29):detail,22,151,12,muted,false);
            if(!Double.isNaN(value))bar(c,174,width,value,accent);text(c,Double.isNaN(value)?"Sensor unavailable":"PC connected",22,212,12,muted,false);
        }
        c.restore();
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        if(bambuSpec==null)return super.onTouchEvent(event);
        if(event.getAction()==MotionEvent.ACTION_UP){performClick();return true;}return true;
    }
    @Override public boolean performClick(){super.performClick();if(bambuSpec!=null)BambuTile.expand(this,bambuSpec);return true;}
}
