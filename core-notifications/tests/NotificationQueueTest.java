package dk.ultrabarx.notifications;

import static dk.ultrabarx.notifications.NotificationQueue.Admission.*;

public final class NotificationQueueTest {
    private static void expect(Object expected, Object actual) {
        if (!java.util.Objects.equals(expected, actual)) {
            throw new AssertionError("Expected " + expected + ", got " + actual);
        }
    }

    public static void main(String[] args) {
        NotificationQueue<Integer> queue = new NotificationQueue<>();
        expect(START, queue.offer(1, 0));
        for (int i = 1; i <= 3; i++) expect(QUEUED, queue.offer(1, i));
        expect(FULL, queue.offer(1, -1));
        for (int i = 4; i <= 6; i++) expect(QUEUED, queue.offer(2, i));
        for (int i = 7; i <= 8; i++) expect(QUEUED, queue.offer(3, i));
        expect(FULL, queue.offer(4, -1));

        expect(1, queue.next());
        expect(QUEUED, queue.offer(1, 9));
        for (int i = 2; i <= 9; i++) expect(i, queue.next());
        expect(null, queue.next());

        expect(START, queue.offer(1, 10));
        expect(QUEUED, queue.offer(1, 11));
        queue.clear();
        expect(START, queue.offer(1, 12));
        expect(null, queue.next());
        System.out.println("Notification queue tests passed");
    }
}
