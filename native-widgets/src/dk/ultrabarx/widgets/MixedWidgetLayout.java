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
        final int[][] cells;

        State(RecyclerView list, int[][] cells) {
            this.list = list;
            this.cells = cells;
            manager = list.getLayoutManager();
            leftPadding = list.getPaddingLeft();
            int gapId = list.getResources().getIdentifier("dp_20", "dimen", "com.ultrabar.launch");
            gap = list.getResources().getDimensionPixelSize(gapId);
            width = (int) (((list.getWidth() - gap * 6) / 5f - gap) / 2f);
            height = list.getHeight() / 2 - gap * 3 / 2;
            decoration = spacing(gap, width, height, list.getHeight(), cells);
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
        String profileId = (String) profile.getClass().getMethod("getId").invoke(profile);
        JSONObject layout = profiles.optJSONObject(profileId);
        JSONArray ids = layout == null ? profiles.optJSONArray(profileId) : layout.getJSONArray("small");
        JSONObject coordinates = layout == null ? null : layout.getJSONObject("positions");
        if (ids == null || (ids.length() == 0 && coordinates == null)) { restore(); return true; }
        Set<String> selected = new HashSet<>();
        for (int i = 0; i < ids.length(); i++) selected.add(ids.getString(i));
        return apply(home, selected, coordinates);
    }

    private static boolean apply(Activity home, Set<String> selected, JSONObject coordinates)
            throws ReflectiveOperationException, JSONException {
        int listId = home.getResources().getIdentifier("recycle_view", "id", "com.ultrabar.launch");
        View view = home.findViewById(listId);
        if (!(view instanceof RecyclerView)) return false;
        RecyclerView list = (RecyclerView) view;
        if (list.getHeight() <= 0 || list.isComputingLayout()) return false;

        Field data = home.getClass().getDeclaredField("mData");
        data.setAccessible(true);
        List<?> widgets = (List<?>) data.get(home);
        if (widgets.isEmpty()) { restore(); return false; }
        int[][] cells = cells(widgets, selected, coordinates);
        if (active != null && active.list == list && Arrays.deepEquals(active.cells, cells)) return true;
        restore();
        if (list.getLayoutManager() == null || list.getAdapter() == null) return false;
        State next = new State(list, cells);
        GridLayoutManager grid = new GridLayoutManager(list.getContext(), 2, 0, false);
        grid.setSpanSizeLookup(new GridLayoutManager.SpanSizeLookup() {
            @Override public int getSpanSize(int position) {
                return position >= 0 && position < cells.length && cells[position][3] == 1 ? 1 : 2;
            }
        });
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

    // Each entry stores the column, row, width in cells, span size and skipped columns.
    private static int[][] cells(List<?> widgets, Set<String> small, JSONObject coordinates)
            throws ReflectiveOperationException, JSONException {
        int[][] cells = new int[widgets.size()][5];
        int column = 0, row = 0;
        for (int i = 0; i < widgets.size(); i++) {
            Object widget = widgets.get(i);
            String id = (String) widget.getClass().getMethod("getId").invoke(widget);
            boolean compact = small.contains(id);
            Object type = widget.getClass().getMethod("getType").invoke(widget);
            int width = compact ? 1 : "TIME".equals(String.valueOf(type)) ? 4 : 2;
            if (!compact && row == 1) { column++; row = 0; }
            JSONArray explicit = coordinates == null ? null : coordinates.optJSONArray(id);
            cells[i][0] = explicit == null ? column : explicit.getInt(0);
            cells[i][1] = explicit == null ? row : explicit.getInt(1);
            cells[i][2] = width;
            if (!compact) column += width;
            else { if (row == 1) column++; row = 1 - row; }
        }
        int previousEnd = 0;
        for (int i = 0; i < cells.length; i++) {
            int[] cell = cells[i];
            int missing = Math.max(0, cell[0] - previousEnd);
            cell[3] = 2;
            cell[4] = missing;
            if (cell[2] == 1 && i + 1 < cells.length && cells[i + 1][0] == cell[0]) {
                cell[3] = 1;
                cells[i + 1][3] = 1;
                cells[i + 1][4] = missing;
                i++;
            }
            previousEnd = cell[0] + cell[2];
        }
        return cells;
    }

    private static RecyclerView.ItemDecoration spacing(int gap, int width, int height, int viewportHeight, int[][] cells) {
        return new RecyclerView.ItemDecoration() {
            @Override public void getItemOffsets(Rect out, View item, RecyclerView parent, RecyclerView.State state) {
                GridLayoutManager.LayoutParams params = (GridLayoutManager.LayoutParams) item.getLayoutParams();
                int position = parent.getChildAdapterPosition(item);
                if (position < 0 || position >= cells.length) return;
                int[] cell = cells[position];
                boolean small = cell[2] == 1;
                // GridLayoutManager asks for decoration offsets after assigning spans and before measuring.
                if (small) {
                    if (!originalSizes.containsKey(item)) originalSizes.put(item, new Point(params.width, params.height));
                    params.width = width;
                    params.height = height;
                } else {
                    Point previous = originalSizes.remove(item);
                    if (previous != null) restoreSize(params, previous);
                }
                int half = gap / 2, top = gap, bottom = gap;
                if (small && cell[3] == 1) {
                    if (cell[1] == 1) top = half;
                    else bottom = gap - half;
                } else if (small) {
                    if (cell[1] == 1) top = viewportHeight - gap - height;
                    bottom = viewportHeight - top - height;
                }
                out.set(cell[4] * (width + gap), top, gap, bottom);
            }
        };
    }
}
