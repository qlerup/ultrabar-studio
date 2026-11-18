package dk.ultrabarx.widgets;

public class BambuPresentationTest {
    private static void check(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) {
        check(!BambuPresentation.downward(0,5,8));
        check(!BambuPresentation.downward(60,20,8));
        check(!BambuPresentation.downward(0,-80,8));
        check(BambuPresentation.downward(5,50,8));
        check(!BambuPresentation.dismiss(10,240,8));
        check(BambuPresentation.dismiss(50,240,8));
        check(BambuPresentation.fittedTextSize(52, 86, 110) == 52);
        check(BambuPresentation.fittedTextSize(52, 120, 110) < 52);
        check(Math.abs(BambuPresentation.fittedTextSize(52, 120, 110) * 120 / 52 - 110) < .01f);
        System.out.println("Bambu presentation checks passed");
    }
}
