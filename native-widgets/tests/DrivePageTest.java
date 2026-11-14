import dk.ultrabarx.widgets.DrivePage;

public class DrivePageTest {
    public static void main(String[] args) {
        int[][] cases={{0,0,0},{1,6000,0},{2,12000,0},{3,0,0},{3,6000,2},{3,12000,0},{5,0,0},{5,6000,2},{5,12000,4},{5,18000,0}};
        for(int[] test:cases)if(DrivePage.start(test[0],test[1])!=test[2])throw new AssertionError("Incorrect two-drive page");
        System.out.println("PASS: two-drive pages, odd counts, six-second rotation and wraparound");
    }
}
