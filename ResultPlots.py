from itertools import chain
from typing import Dict
from dearpygui.dearpygui import *
import HGBDiceStats as stats

PLOT_HEIGHT = 450
PLOT_WIDTH = 425
BAR_WIDTH = 0.8

analyses = {**stats.BASIC_ANALYSES, **stats.STATUS_ANALYSES}


def show_plots(show: Tuple[str], hide: Tuple[str]):
    def callback(sender, app_data):
        if app_data[0] != 0:
            return
        nonlocal show, hide
        for plot in hide:
            hide_item(plot)
        for plot in show:
            show_item(plot)

    return callback


def skip_plot(result: Dict[str, Any]) -> bool:
    return (
        result["average"] == 0
        and len(result["totals"]) < 2
        and not analyses[result["name"]].show_if_missing
    )


# TODO: Create and delete series/plots on demand within window
def graph_results(
    window: int,
    tests: List[Dict],
    test_names: List[str],
):
    push_container_stack(window)
    add_text("Click plots to cycle between analysis types!")
    # TODO: Add dropdown for comparisons
    # TODO: Recalc max cols for multiple tests
    # cols = max(len(res.get("by_source", [])) for res in test) + 1
    cols = 7  # TODO: See if this is even necessary
    with table(
        header_row=False,
        resizable=False,
        policy=mvTable_SizingFixedSame,
        borders_outerH=False,
        borders_outerV=False,
        borders_innerH=False,
        borders_innerV=True,
        scrollX=True,
        scrollY=True,
    ):
        for _ in range(cols):
            add_table_column(
                width=PLOT_WIDTH + 5,
                width_fixed=True,
                no_resize=True,
                no_reorder=True,
                no_sort=True,
            )
        for name in analyses:
            # skip missing
            if all(skip_plot(test[name]) for test in tests):
                continue
            base_plots, normal_plots, min_plots = plot_result(
                [test[name] for test in tests], test_names
            )

            base_handler = add_item_handler_registry()
            normal_handler = add_item_handler_registry()
            min_handler = add_item_handler_registry()

            add_item_clicked_handler(
                parent=base_handler,
                callback=show_plots(normal_plots, base_plots + min_plots),
            )

            if min_plots:
                show = min_plots
                hide = base_plots + normal_plots
            else:
                show = base_plots
                hide = normal_plots
            add_item_clicked_handler(
                parent=normal_handler, callback=show_plots(show, hide)
            )

            add_item_clicked_handler(
                parent=min_handler,
                callback=show_plots(base_plots, normal_plots + min_plots),
            )

            for plot in base_plots:
                bind_item_handler_registry(plot, base_handler)
            for plot in normal_plots:
                bind_item_handler_registry(plot, normal_handler)
                hide_item(plot)
            for plot in min_plots:
                bind_item_handler_registry(plot, min_handler)
                hide_item(plot)

    pop_container_stack()


def plot_result(
    results: List[Dict[str, Any]], test_names: List[str]
) -> Tuple[Tuple[int]]:
    if results[0]["type"] == stats.AnalysisType.BOOL:
        normal_label = f"WHEN {results[0]['name']} is True"
    else:
        normal_label = f"WHEN {results[0]['name']} > 0"
    base_label = f"{results[0]['name']}"
    min_label = f"{results[0]['name']} AT LEAST X:"
    groups = []
    with table_row(height=PLOT_HEIGHT + 5):
        groups.append(
            make_plot_group(results, (base_label, normal_label, min_label), test_names)
        )
        # TODO: Handle sources
        return tuple(tuple(p for p in g if p is not None) for g in zip(*groups))
        sources = results.get("by_source", [])
        for source in sources:
            if results["type"] == stats.AnalysisType.BOOL:
                avg = f"{source['average']:0.1%}"
                normal_label = (
                    f"WHEN {results['name']} is True:"
                    + f"\n{results['name']} from {source['name']}"
                    + f" (Avg: {source['normalized_average']:0.1%})"
                )
            else:
                avg = f"{source['average']:0.2f}"
                normal_label = (
                    f"WHEN {results['name']} > 0:"
                    + f"\n{results['name']} from {source['name']}"
                    + f" (Avg: {source['normalized_average']:0.2f})"
                )
            min_label = (
                f"{results['name']} AT LEAST X:"
                + f"\n{results['name']} from {source['name']}"
            )
            base_label = f"{results['name']} from {source['name']} (Avg: {avg})"
            groups.append(
                make_plot_group(source, (base_label, normal_label, min_label))
            )
    # transpose and return list of groups
    return tuple(tuple(p for p in g if p is not None) for g in zip(*groups))


def make_plot_group(
    results: List[Dict], labels: Tuple[str], test_names: List[str]
) -> Tuple[int]:
    base_label, normal_label, min_label = labels
    with table_cell():
        base_plot = bar_plot(
            label=base_label,
            height=PLOT_HEIGHT,
            width=PLOT_WIDTH,
            data_x=[[float(k) for k in res["totals"].keys()] for res in results],
            data_y=[[float(v) for v in res["totals"].values()] for res in results],
            names=test_names,
            datatype=results[0]["type"],
        )
        normal_plot = bar_plot(
            label=normal_label,
            height=PLOT_HEIGHT,
            width=PLOT_WIDTH,
            data_x=[
                [float(k) for k in res["normalized_totals"].keys()] for res in results
            ],
            data_y=[
                [float(v) for v in res["normalized_totals"].values()] for res in results
            ],
            names=test_names,
            datatype=results[0]["type"],
        )
        min_plot = None
        if results[0].get("min_totals", None):
            min_plot = bar_plot(
                label=min_label,
                height=PLOT_HEIGHT,
                width=PLOT_WIDTH,
                data_x=[
                    [float(k) for k in res["min_totals"].keys()] for res in results
                ],
                data_y=[
                    [float(v) for v in res["min_totals"].values()] for res in results
                ],
                names=test_names,
                datatype=results[0]["type"],
            )

    return (base_plot, normal_plot, min_plot)


def bar_plot(
    label: str,
    height: int,
    width: int,
    data_x: List[List[float]],
    data_y: List[List[float]],
    names: List[str],
    datatype: stats.AnalysisType,
) -> int:
    plot = add_plot(
        label=label,
        height=height,
        width=width,
        no_mouse_pos=True,
    )
    add_plot_legend(parent=plot)

    x_min = min(chain.from_iterable(data_x)) - 0.8
    x_max = max(chain.from_iterable(data_x)) + 0.8
    y_max = max(chain.from_iterable(data_y)) * 1.2

    x_axis = add_plot_axis(parent=plot, axis=mvXAxis)
    if datatype == stats.AnalysisType.BOOL:
        set_axis_ticks(x_axis, (("No", 0), ("Yes", 1)))
    elif datatype == stats.AnalysisType.RANGE:
        labels = [str(int(x)) for x in chain.from_iterable(data_x)]
        set_axis_ticks(x_axis, tuple(zip(labels, chain.from_iterable(data_x))))
    y_label = "Probability %"
    y_axis = add_plot_axis(parent=plot, axis=mvYAxis, label=y_label)
    labels = [f"{y:0.2%}" for y in chain.from_iterable(data_y)]
    set_axis_ticks(y_axis, tuple(zip(labels, chain.from_iterable(data_y))))

    for idx, (series_x, series_y, name) in enumerate(zip(data_x, data_y, names)):
        weight = BAR_WIDTH / len(data_y)
        left = (len(data_y) - 1) * -(weight / 2)
        offset = left + (idx * weight)
        # Dummy missing data
        if not series_x:
            series_x = [0.0]
            series_y = [1.0]
        add_bar_series(
            [x + offset for x in series_x],
            series_y,
            label=name,
            parent=y_axis,
            weight=weight,
        )
    set_axis_limits(x_axis, ymin=x_min, ymax=x_max)
    set_axis_limits(y_axis, ymin=0.0, ymax=y_max)

    return plot
