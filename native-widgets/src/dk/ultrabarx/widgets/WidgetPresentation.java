package dk.ultrabarx.widgets;

import android.graphics.*;
import org.json.*;

/** Bounded vector/text presets supplied by an installed package, independent of brand. */
final class WidgetPresentation {
    static String label(JSONObject spec,String key,String fallback){
        JSONObject presentation=spec==null?null:spec.optJSONObject("_presentation");
        JSONObject labels=presentation==null?null:presentation.optJSONObject("labels");
        return labels==null?fallback:labels.optString(key,fallback);
    }
    static boolean hasArtwork(JSONObject spec){
        JSONObject p=spec==null?null:spec.optJSONObject("_presentation");
        JSONArray shapes=p==null?null:p.optJSONArray("artwork");
        return shapes!=null&&shapes.length()>0;
    }
    static void draw(Canvas canvas,JSONObject spec,float x,float y,float size,int accent){
        if(!hasArtwork(spec))return;
        JSONArray shapes=spec.optJSONObject("_presentation").optJSONArray("artwork");
        Paint paint=new Paint(3);canvas.save();canvas.translate(x,y);canvas.scale(size/100f,size/100f);
        try{
            for(int i=0;i<Math.min(shapes.length(),64);i++){
                JSONObject shape=shapes.optJSONObject(i);if(shape==null)continue;
                JSONArray points=shape.optJSONArray("points");if(points==null||points.length()<4)continue;
                String fill=shape.optString("fill");paint.setColor(fill.equals("accent")?accent:Color.parseColor(fill));
                float a=(float)points.optDouble(0),b=(float)points.optDouble(1),c=(float)points.optDouble(2),d=(float)points.optDouble(3);
                switch(shape.optString("type")){
                    case "rect":canvas.drawRect(a,b,c,d,paint);break;
                    case "roundRect":canvas.drawRoundRect(a,b,c,d,(float)points.optDouble(4),(float)points.optDouble(5),paint);break;
                    case "oval":canvas.drawOval(a,b,c,d,paint);break;
                    case "polygon":
                        Path path=new Path();path.moveTo(a,b);
                        for(int j=2;j+1<Math.min(points.length(),32);j+=2)path.lineTo((float)points.optDouble(j),(float)points.optDouble(j+1));
                        path.close();canvas.drawPath(path,paint);break;
                }
            }
        }catch(Exception ignored){/* Invalid local telemetry cannot crash the home screen. */}
        finally{canvas.restore();}
    }
}
