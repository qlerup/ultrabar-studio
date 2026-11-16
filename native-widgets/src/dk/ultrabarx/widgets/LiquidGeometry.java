package dk.ultrabarx.widgets;

/** Pure geometry shared by runtime and regression tests. */
public final class LiquidGeometry {
    public static float spring(float time) {
        if (time <= 0) return 0; if (time >= 1) return 1;
        return (float)(1 - Math.exp(-7.5 * time) * Math.cos(9 * time));
    }
    public static float width(float source, float viewport, int slots) {
        return width(source,0,viewport,slots);
    }
    public static float width(float source, float gap, float viewport, int slots) {
        if (slots < 2 || slots > 5 || source <= 0 || viewport <= 0) throw new IllegalArgumentException("Invalid liquid panel size");
        return Math.min(viewport, source * slots+gap*(slots-1));
    }
    public static int startSlot(int position,int expandedSlots,int visibleSlots){
        if(visibleSlots<expandedSlots||position<0||position>=visibleSlots)throw new IllegalArgumentException("Invalid row position");
        return Math.max(0,Math.min(position-(expandedSlots-1)/2,visibleSlots-expandedSlots));
    }
    public static float left(float sourceLeft, float width, float viewportLeft, float viewportWidth) {
        return Math.max(viewportLeft, Math.min(sourceLeft, viewportLeft + viewportWidth - width));
    }
}
