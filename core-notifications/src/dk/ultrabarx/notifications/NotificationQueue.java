package dk.ultrabarx.notifications;

import java.util.ArrayDeque;

/** Serializes admission from Binder threads and delivery on the main thread. */
final class NotificationQueue<T> {
    enum Admission { START, QUEUED, FULL }

    private static final int MAX_WAITING = 8;
    private static final int MAX_PER_SENDER = 3;

    private final ArrayDeque<Entry<T>> waiting = new ArrayDeque<>();
    private boolean running;

    synchronized Admission offer(int sender, T notification) {
        if (!running) {
            running = true;
            return Admission.START;
        }
        if (waiting.size() == MAX_WAITING) return Admission.FULL;
        int fromSender = 0;
        for (Entry<T> entry : waiting) {
            if (entry.sender == sender && ++fromSender == MAX_PER_SENDER) {
                return Admission.FULL;
            }
        }
        waiting.addLast(new Entry<>(sender, notification));
        return Admission.QUEUED;
    }

    synchronized T next() {
        Entry<T> entry = waiting.pollFirst();
        if (entry != null) return entry.notification;
        running = false;
        return null;
    }

    synchronized void clear() {
        waiting.clear();
        running = false;
    }

    private static final class Entry<T> {
        final int sender;
        final T notification;

        Entry(int sender, T notification) {
            this.sender = sender;
            this.notification = notification;
        }
    }
}
