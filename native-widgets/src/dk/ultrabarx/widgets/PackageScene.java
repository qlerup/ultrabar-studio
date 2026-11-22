package dk.ultrabarx.widgets;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.RectF;
import android.util.Base64;
import android.util.LruCache;
import android.view.View;
import java.util.Calendar;
import org.json.JSONArray;
import org.json.JSONObject;

/** Composites pixels built from the installed widget layout. Time layers tick locally. */
final class PackageScene {
    private static final LruCache<String,Bitmap> bitmaps = new LruCache<String,Bitmap>(6*1024*1024) {
        protected int sizeOf(String key, Bitmap value) { return value.getByteCount()+key.length()*2; }
    };
    private static final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
    private static Bitmap image(String key, JSONObject images) {
        Bitmap bitmap=bitmaps.get(key);
        if(bitmap!=null)return bitmap;
        String encoded=images==null?key:images.optString(key);
        if(bitmap==null && !encoded.isEmpty() && encoded.length()<524288) {
            byte[] bytes=Base64.decode(encoded,Base64.DEFAULT);
            bitmap=BitmapFactory.decodeByteArray(bytes,0,bytes.length);
            if(bitmap!=null)bitmaps.put(key,bitmap);
        }
        return bitmap;
    }
    private static String value(JSONObject layer, Calendar date) {
        int hour=date.get(Calendar.HOUR_OF_DAY),day=date.get(Calendar.DAY_OF_MONTH),month=date.get(Calendar.MONTH);
        String type=layer.optString("value");
        if(type.equals("date") || type.equals("shortDate")){
            String text=day+" "+layer.optJSONArray("months").optString(month);
            if(type.equals("shortDate"))return text;
            return layer.optJSONArray("days").optString((date.get(Calendar.DAY_OF_WEEK)+5)%7)+", "+text+" "+date.get(Calendar.YEAR);
        }
        if(type.equals("period"))return hour<12?"AM":"PM";
        int n=type.equals("minutes")?date.get(Calendar.MINUTE):type.equals("seconds")?date.get(Calendar.SECOND):
            layer.optBoolean("twelve")?(hour+11)%12+1:hour;
        return n<10?"0"+n:Integer.toString(n);
    }
    private static void text(Canvas c,JSONObject layer,String label,int x,int y,int w,int h,JSONObject images){
        JSONObject glyphs=layer.optJSONObject("glyphs"),spans=glyphs.optJSONObject("spans");
        Bitmap atlas=image(glyphs.optString("png"),images);if(atlas==null)return;
        int width=0,height=glyphs.optInt("height");
        for(char ch:label.toCharArray()){JSONArray s=spans.optJSONArray(String.valueOf(ch));if(s!=null)width+=s.optInt(1);}
        boolean plate=layer.has("plate");
        float scale=Math.min(1f,Math.min(w*(plate?.9f:1f)/Math.max(1,width),(float)h/height));
        float dx=x+(plate?(w-width*scale)/2:0),dy=y+(h-height*scale)/2;
        paint.setColor(Color.WHITE);
        for(char ch:label.toCharArray()){
            JSONArray s=spans.optJSONArray(String.valueOf(ch));if(s==null)continue;
            int sx=s.optInt(0),sw=s.optInt(1);
            c.drawBitmap(atlas,new Rect(sx,0,sx+sw,height),new RectF(dx,dy,dx+sw*scale,dy+height*scale),paint);dx+=sw*scale;
        }
    }
    static boolean draw(View view,Canvas c,JSONObject frame,JSONObject images){
        if(frame==null)return false;
        Bitmap bg=image(frame.optString("png"),images);if(bg==null)return false;
        int width=frame.optInt("width"),height=frame.optInt("height");
        c.save();
        try{
            c.scale((float)view.getWidth()/width,(float)view.getHeight()/height);
            paint.setColor(Color.WHITE);c.drawBitmap(bg,null,new Rect(0,0,width,height),paint);
            JSONArray layers=frame.optJSONArray("layers");
            if(layers==null||layers.length()==0)return true;
            long now=System.currentTimeMillis();
            Calendar date=Calendar.getInstance(),previous=(Calendar)date.clone();
            date.setTimeInMillis(now);previous.setTimeInMillis(now-1000);
            boolean animating=false;
            for(int i=0;i<layers.length();i++){
                JSONObject layer=layers.optJSONObject(i);JSONArray box=layer.optJSONArray("box");
                int x=box.optInt(0),y=box.optInt(1),w=box.optInt(2),h=box.optInt(3);
                String current=value(layer,date),old=value(layer,previous);
                int duration=layer.optInt("duration");float phase=duration==0?1f:Math.min(1f,(now%1000)/(float)duration);
                if(layer.has("plate")&&!current.equals(old)&&phase<1){
                    animating=true;
                    float middle=y+h/2f;
                    c.save();c.clipRect(x,y,x+w,middle);text(c,layer,current,x,y,w,h,images);c.restore();
                    c.save();c.clipRect(x,middle,x+w,y+h);text(c,layer,old,x,y,w,h,images);c.restore();
                    float cosine=(float)Math.cos(Math.PI*phase);boolean upper=cosine>=0;
                    c.save();c.scale(1f,Math.abs(cosine),x,middle);c.clipRect(x+1,upper?y:middle,x+w-1,upper?middle:y+h);
                    paint.setColor(Color.parseColor(layer.optString("plate")));c.drawRect(x,y,x+w,y+h,paint);
                    text(c,layer,upper?old:current,x,y,w,h,images);c.restore();
                }else text(c,layer,current,x,y,w,h,images);
                if(layer.has("plate")){
                    paint.setColor(Color.parseColor(layer.optString("seam")));c.drawRect(x,y+h/2,x+w,y+h/2+1,paint);
                }
            }
            view.postInvalidateDelayed(animating?40:1002-now%1000);
            return true;
        }finally{c.restore();}
    }
}
