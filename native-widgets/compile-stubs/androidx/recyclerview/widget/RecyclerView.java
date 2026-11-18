package androidx.recyclerview.widget;

import android.graphics.Rect;
import android.view.View;
import android.view.ViewGroup;

/** Compile-time signatures. LineOS supplies the implementation at runtime. */
public abstract class RecyclerView extends ViewGroup {
    private RecyclerView() { super(null); }

    public abstract LayoutManager getLayoutManager();
    public abstract void setLayoutManager(LayoutManager manager);
    public abstract Adapter getAdapter();
    public abstract RecycledViewPool getRecycledViewPool();
    public abstract boolean isComputingLayout();
    public abstract int getItemDecorationCount();
    public abstract ItemDecoration getItemDecorationAt(int index);
    public abstract void addItemDecoration(ItemDecoration decoration);
    public abstract void removeItemDecoration(ItemDecoration decoration);

    public abstract static class LayoutManager {}
    public abstract static class Adapter {
        public abstract void notifyDataSetChanged();
    }
    public abstract static class RecycledViewPool {
        public abstract void clear();
    }

    public static class State {}

    public abstract static class ItemDecoration {
        public void getItemOffsets(Rect offsets, View view, RecyclerView parent, State state) {}
    }
}
