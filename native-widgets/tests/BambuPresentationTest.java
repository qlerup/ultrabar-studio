package dk.ultrabarx.widgets;

public class BambuPresentationTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) {
        check(BambuPresentation.nozzleLabel("h2d",0).equals("LEFT NOZZLE"));
        check(BambuPresentation.nozzleLabel("h2d",1).equals("RIGHT NOZZLE"));
        check(BambuPresentation.nozzleLabel("h2d",2).equals("NOZZLE T2"));
        check(BambuPresentation.nozzleLabel("generic",0).equals("NOZZLE T0"));
        check(BambuPresentation.nozzleLabel("h3c",8).equals("NOZZLE T8"));
        check(!BambuPresentation.downward(0,5,8));
        check(!BambuPresentation.downward(60,20,8));
        check(!BambuPresentation.downward(0,-80,8));
        check(BambuPresentation.downward(5,50,8));
        check(!BambuPresentation.dismiss(10,240,8));
        check(BambuPresentation.dismiss(50,240,8));
        System.out.println("Bambu presentation checks passed");
    }
}
