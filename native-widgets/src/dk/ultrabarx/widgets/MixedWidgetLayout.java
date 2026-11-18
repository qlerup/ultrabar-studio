package dk.ultrabarx.widgets;

import android.app.Activity;
import android.graphics.Point;
import android.graphics.Rect;
import android.view.View;
import android.view.ViewGroup;
import androidx.recyclerview.widget.GridLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.BitSet;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.WeakHashMap;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/** Uses the launcher RecyclerView so stock cards keep their normal binding and actions. */
public final class MixedWidgetLayout {
    private MixedWidgetLayout() {}
    private static final WeakHashMap<View, Point> originalSizes = new WeakHashMap<>();
    private static MixedWidgetLayout.State active;

    private static final class State {
        final RecyclerView list;
        final RecyclerView.LayoutManager manager;
        final List<RecyclerView.ItemDecoration> removed = new ArrayList<>();
        final RecyclerView.ItemDecoration decoration;
        final int leftPadding, gap, width, height;
        final Set<String> ids;
        final int[] positions;

        State(RecyclerView list, Set<String> ids, int[] positions) {
            this.list = list;
            this.ids = ids;
            this.positions = positions;
            manager = list.getLayoutManager();
            leftPadding = list.getPaddingLeft();
            int gapId = list.getResources().getIdentifier("dp_20", "dimen", "com.ultrabar.launch");
            gap = list.getResources().getDimensionPixelSize(gapId);
            width = (int) (((list.getWidth() - gap * 6) / 5f - gap) / 2f);
            height = list.getHeight() / 2 - gap * 3 / 2;
            decoration = spacing(gap, width, height);
        }
    }

    public static boolean apply(Activity home, String configured) throws ReflectiveOperationException, JSONException {
        JSONObject profiles = new JSONObject(configured);
        if (active != null && active.list.isComputingLayout()) return false;
        if (profiles.length() == 0) { restore(); return true; }
        if (home == null) return false;
        Class<?> preferences = home.getClassLoader().loadClass("com.ultrabar.launch.common.utils.SharedPreferencesUtils");
        Object instance = preferences.getMethod("getIns").invoke(null);
        Object profile = preferences.getMethod("getProfile").invoke(instance);
        JSONArray ids = profiles.optJSONArray((String) profile.getClass().getMethod("getId").invoke(profile));
        if (ids == null || ids.length() == 0) { restore(); return true; }
        Set<String> selected = new HashSet<>();
        for (int i = 0; i < ids.length(); i++) selected.add(ids.getString(i));
        return apply(home, selected);
    }

    private static boolean apply(Activity home, Set<String> selected) throws ReflectiveOperationException {
        if (active != null && active.list.isComputingLayout()) return false;
        int listId = home.getResources().getIdentifier("recycle_view", "id", "com.ultrabar.launch");
        View view = home.findViewById(listId);
        if (!(view instanceof RecyclerView)) return false;
        RecyclerView list = (RecyclerView) view;
        if (list.getHeight() <= 0 || list.isComputingLayout()) return false;

        Field data = home.getClass().getDeclaredField("mData");
        data.setAccessible(true);
        List<?> widgets = (List<?>) data.get(home);
        int[] matches = new int[widgets.size()];
        int count = 0;
        for (int index = 0; index < widgets.size(); index++) {
            Object widget = widgets.get(index);
            if (selected.contains(widget.getClass().getMethod("getId").invoke(widget))) matches[count++] = index;
        }
        if (count == 0) { restore(); return false; }
        int[] positions = Arrays.copyOf(matches, count);
        if (active != null && active.list == list && active.ids.equals(selected) && Arrays.equals(active.positions, positions)) return true;
        restore();
        if (list.getLayoutManager() == null || list.getAdapter() == null) return false;
        State next = new State(list, selected, positions);
        GridLayoutManager grid = new GridLayoutManager(list.getContext(), 2, 0, false);
        grid.setSpanSizeLookup(spans(positions));
        while (list.getItemDecorationCount() > 0) {
            RecyclerView.ItemDecoration old = list.getItemDecorationAt(0);
            next.removed.add(old);
            list.removeItemDecoration(old);
        }
        active = next;
        try {
            list.setLayoutManager(grid);
            list.setPadding(next.leftPadding + next.gap, list.getPaddingTop(), list.getPaddingRight(), list.getPaddingBottom());
            list.addItemDecoration(next.decoration);
            list.getAdapter().notifyDataSetChanged();
        } catch (RuntimeException failure) {
            restore();
            throw failure;
        }
        return true;
    }

    private static void restore() {
        State old = active;
        if (old == null) return;
        active = null;
        RecyclerView list = old.list;
        for (Map.Entry<View, Point> entry : originalSizes.entrySet()) {
            View view = entry.getKey();
            ViewGroup.LayoutParams params = view == null ? null : view.getLayoutParams();
            if (params != null) restoreSize(params, entry.getValue());
        }
        originalSizes.clear();
        list.removeItemDecoration(old.decoration);
        list.setLayoutManager(old.manager);
        list.getRecycledViewPool().clear();
        list.setPadding(old.leftPadding, list.getPaddingTop(), list.getPaddingRight(), list.getPaddingBottom());
        for (RecyclerView.ItemDecoration decoration : old.removed) list.addItemDecoration(decoration);
        if (list.getAdapter() != null) list.getAdapter().notifyDataSetChanged();
    }

    private static void restoreSize(ViewGroup.LayoutParams params, Point size) {
        params.width = size.x;
        params.height = size.y;
    }

    public static GridLayoutManager.SpanSizeLookup spans(int[] smallPositions) {
        BitSet small = new BitSet();
        for (int position : smallPositions) small.set(position);
        return new GridLayoutManager.SpanSizeLookup() {
            @Override public int getSpanSize(int position) {
                return position >= 0 && small.get(position) ? 1 : 2;
            }
        };
    }

    private static RecyclerView.ItemDecoration spacing(int gap, int width, int height) {
        return new RecyclerView.ItemDecoration() {
            @Override public void getItemOffsets(Rect out, View item, RecyclerView parent, RecyclerView.State state) {
                GridLayoutManager.LayoutParams params = (GridLayoutManager.LayoutParams) item.getLayoutParams();
                boolean small = params.getSpanSize() == 1;
                // GridLayoutManager asks for decoration offsets after assigning spans and before measuring.
                if (small) {
                    if (!originalSizes.containsKey(item)) originalSizes.put(item, new Point(params.width, params.height));
                    params.width = width;
                    params.height = height;
                } else {
                    Point previous = originalSizes.remove(item);
                    if (previous != null) restoreSize(params, previous);
                }
                boolean lower = params.getSpanIndex() == 1;
                int half = gap / 2;
                out.set(0, small && lower ? half : gap, gap, small && !lower ? gap - half : gap);
            }
        };
    }
}
