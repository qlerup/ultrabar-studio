package dk.ultrabarx.widgets;

final class BambuPresentation {
    static boolean downward(float dx, float dy, float slop) {
        return dy > slop && dy > Math.abs(dx) * 1.4f;
    }
    static boolean dismiss(float distance, float height, float slop) {
        return distance > Math.max(slop * 3, height * .18f);
    }
}
