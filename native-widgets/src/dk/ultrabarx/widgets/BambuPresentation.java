package dk.ultrabarx.widgets;

final class BambuPresentation {
    static String nozzleLabel(String model, int tool) {
        return model.equals("h2d") && tool >= 0 && tool < 2
            ? (tool == 0 ? "LEFT NOZZLE" : "RIGHT NOZZLE") : "NOZZLE T" + tool;
    }
    static boolean downward(float dx, float dy, float slop) {
        return dy > slop && dy > Math.abs(dx) * 1.4f;
    }
    static boolean dismiss(float distance, float height, float slop) {
        return distance > Math.max(slop * 3, height * .18f);
    }
}
