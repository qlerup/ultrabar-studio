package androidx.recyclerview.widget;

import android.content.Context;
import android.view.ViewGroup;

/** Compile-time signatures. LineOS supplies the implementation at runtime. */
public class GridLayoutManager extends RecyclerView.LayoutManager {
    public GridLayoutManager(Context context, int spanCount, int orientation, boolean reverse) {}

    public void setSpanSizeLookup(SpanSizeLookup lookup) {}
    public abstract static class SpanSizeLookup {
        public abstract int getSpanSize(int position);
    }

    public abstract static class LayoutParams extends ViewGroup.MarginLayoutParams {
        private LayoutParams() { super(0, 0); }
        public abstract int getSpanSize();
        public abstract int getSpanIndex();
    }
}
