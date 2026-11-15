import dk.ultrabarx.widgets.LiquidGeometry;
public final class LiquidGeometryTest {
    static void check(boolean condition){if(!condition)throw new AssertionError();}
    public static void main(String[] args){
        check(LiquidGeometry.spring(0)==0);check(LiquidGeometry.spring(1)==1);
        for(int i=0;i<=100;i++){float f=LiquidGeometry.spring(i/100f);check(Float.isFinite(f)&&f>=0&&f<1.12f);}
        for(int slots=2;slots<=5;slots++){
            check(LiquidGeometry.width(240,1400,slots)==240*slots);
            float width=LiquidGeometry.width(300,1200,slots);check(width<=1200);
            for(float left:new float[]{0,240,480,960,1200}){float x=LiquidGeometry.left(left,width,10,1200);check(x>=10&&x+width<=1210);}
        }
        for(int slots:new int[]{-1,0,1,6,99}){boolean bad=false;try{LiquidGeometry.width(240,1400,slots);}catch(IllegalArgumentException e){bad=true;}check(bad);}
        System.out.println("PASS: liquid spring endpoints, bounded overshoot, all 2–5 slot widths and edge anchors");
    }
}
