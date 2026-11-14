package dk.ultrabarx.widgets;

public final class DrivePage {
    private DrivePage() {}
    public static int start(int drives,long elapsedMillis) {
        if(drives<=2)return 0;
        return (int)((Math.max(0,elapsedMillis)/6000)%((drives+1)/2))*2;
    }
}
