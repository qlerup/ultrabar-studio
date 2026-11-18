package dk.ultrabarx.widgets;

import android.graphics.*;

/** Small model-specific, three-quarter printer illustrations, rendered without network assets. */
final class PrinterPortrait {
    static void draw(Canvas c, String model, float x, float y, float size, int accent) {
        if (model.equals("generic")) return;
        c.save(); c.translate(x,y); c.scale(size/100f,size/100f);
        Paint p=new Paint(3);
        if(model.equals("a1")||model.equals("a1-mini")){
            boolean mini=model.equals("a1-mini");
            p.setColor(0x30000000);c.drawOval(3,85,98,99,p);
            p.setColor(0xffafb9bc);c.drawRoundRect(8,82,92,93,4,4,p);
            p.setColor(0xff526166);c.drawRect(18,70,70,82,p);
            p.setColor(0xffd5dbdd);c.drawRect(mini?65:73,10,mini?72:80,85,p);
            if(!mini)c.drawRect(18,10,25,85,p);
            c.drawRect(12,27,86,33,p);
            p.setColor(0xffe9edef);c.drawRoundRect(37,24,51,42,3,3,p);
            p.setColor(accent);c.drawRect(41,39,47,44,p);
            p.setColor(0xff263238);c.drawRoundRect(74,74,89,83,2,2,p);
            p.setColor(0xffb7c0c3);c.drawCircle(mini?81:51,mini?14:8,9,p);
            p.setColor(0xff46565b);c.drawCircle(mini?81:51,mini?14:8,3,p);
            c.restore();return;
        }
        boolean open=model.equals("a1")||model.equals("a1-mini")||model.equals("p1p");
        boolean h=model.startsWith("h2");
        int shell=model.startsWith("x1")||model.equals("a1")||model.equals("a1-mini")?0xffbfc6c9:0xff505c61;
        // Depth, base and top distinguish the wide H series from the compact P/X machines.
        float left=h?5:16, right=h?81:74, top=model.equals("a1-mini")?23:10;
        p.setColor(0x30000000);c.drawOval(left-2,88,98,99,p);
        p.setColor(0xff263238);Path side=new Path();side.moveTo(right,top);side.lineTo(96,top+9);side.lineTo(96,85);side.lineTo(right,94);side.close();c.drawPath(side,p);
        p.setColor(shell);c.drawRoundRect(left,top,right,94,3,3,p);
        p.setColor(0xff172329);c.drawRect(left+5,top+12,right-5,84,p);
        if(open){
            p.setColor(shell);c.drawRect(left+7,top+6,left+12,83,p);c.drawRect(right-12,top+6,right-7,83,p);
            c.drawRect(left+7,top+25,right-7,top+31,p);
            p.setColor(0xffedf1f2);c.drawRoundRect((left+right)/2-7,top+22,(left+right)/2+7,top+38,2,2,p);
        }else{
            p.setColor(0xff334950);c.drawRect(left+8,top+17,right-8,81,p);
            p.setColor(0xff142126);c.drawRect(left+12,top+22,right-12,77,p);
            p.setColor(0xffa9b4b8);c.drawRect(left+12,top+27,right-12,top+30,p);
            p.setColor(0xff69787f);c.drawRect((left+right)/2-7,top+28,(left+right)/2+7,top+41,p);
            if(model.equals("h2d")){p.setColor(accent);c.drawRect((left+right)/2-6,top+40,(left+right)/2-2,top+44,p);c.drawRect((left+right)/2+2,top+40,(left+right)/2+6,top+44,p);}
            p.setColor(0xffa8b8bc);c.drawRoundRect(right-11,50,right-8,61,1,1,p);
        }
        p.setColor(0xff8b9c9f);c.drawRect(left+11,76,right-11,80,p);
        p.setColor(0xff334b42);Path print=new Path();float mid=(left+right)/2;print.moveTo(mid-9,75);print.lineTo(mid-9,64);print.lineTo(mid,59);print.lineTo(mid+9,64);print.lineTo(mid+9,75);print.close();c.drawPath(print,p);
        p.setColor(accent);c.drawRect(left+5,top+3,left+17,top+8,p);
        if(model.equals("x1e")){p.setColor(0xffd4b166);c.drawCircle(right-7,top+6,2,p);}
        if(model.equals("h2c")){p.setColor(0xff7b898f);c.drawRect(left+11,top-5,right-10,top,p);for(int i=0;i<6;i++){p.setColor(i%2==0?accent:0xffbfc6c9);c.drawCircle(left+17+i*8,top-3,2,p);}}
        if(model.equals("h3c")){p.setColor(0xffbfc6c9);c.drawRect(left,top,right,top+12,p);p.setColor(0xff202f34);c.drawRoundRect(left+2,0,right+7,top+7,3,3,p);for(int i=0;i<4;i++){p.setColor(0xff6d8288);c.drawCircle(left+13+i*14,5,5,p);}}
        c.restore();
    }
}
