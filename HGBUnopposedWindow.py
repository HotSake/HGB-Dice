from collections import defaultdict
import traceback
from dearpygui.dearpygui import *
from diceProbs import all_probs_high_die, all_probs_threshold, expected, standard_dev

WINDOW_WIDTH, WINDOW_HEIGHT = 1350, 950
SMALL_INPUT_WIDTH = 50
PLOT_HEIGHT = 425
PLOT_WIDTH = 425
UNOPP_WINDOW = "unopp_setup_window"


def make_unopp_window():
    with window(
        label="Roll Statistics",
        tag=UNOPP_WINDOW,
        height=WINDOW_HEIGHT,
        width=WINDOW_WIDTH,
    ):
        with table(
            header_row=False,
            resizable=False,
            policy=mvTable_SizingFixedSame,
            borders_outerH=False,
            borders_outerV=False,
            borders_innerH=False,
            borders_innerV=True,
        ):
            for _ in range(2):
                add_table_column(
                    width=PLOT_WIDTH + 5,
                    width_stretch=False,
                    no_resize=True,
                    no_reorder=True,
                    no_sort=True,
                )
            with table_row(height=25):
                with group(horizontal=True):
                    add_text("Dice:")
                    add_input_text(
                        tag="dice",
                        width=SMALL_INPUT_WIDTH,
                        default_value=2,
                        callback=update_test,
                    )
                    add_text("  Skill:")
                    add_input_text(
                        tag="skill",
                        width=SMALL_INPUT_WIDTH,
                        default_value=5,
                        callback=update_test,
                    )
                    add_text("  Result Bonus:")
                    add_input_text(
                        tag="result",
                        width=SMALL_INPUT_WIDTH,
                        default_value=0,
                        callback=update_test,
                    )
            with table_row():
                with table_cell():
                    bar_plot(
                        plot_tag="roll1",
                        label=f"Probability of rolling exactly...",
                        height=PLOT_HEIGHT,
                        width=PLOT_WIDTH,
                        tag_x=f"x_roll1",
                        tag_y=f"y_roll1",
                        series="roll1_series",
                    )
                    add_text("", tag="exp1")
                    add_text("", tag="sdev1")
                with table_cell():
                    bar_plot(
                        plot_tag="roll2",
                        label=f"Probability of rolling at least...",
                        height=PLOT_HEIGHT,
                        width=PLOT_WIDTH,
                        tag_x=f"x_roll2",
                        tag_y=f"y_roll2",
                        series="roll2_series",
                    )
                    add_text("", tag="desc_min")

    update_test()


def update_test() -> bool:
    try:
        dice = int(get_value("dice"))
        skill = int(get_value("skill"))
        res_bonus = int(get_value("result"))
        base_rolls = all_probs_high_die(dice=dice, sides=6)
        final_rolls = defaultdict(float)

        for roll, prob in base_rolls.items():
            for bonus, bonus_prob in all_probs_threshold(
                dice=dice - 1, sides=roll, val=skill
            ).items():
                final_rolls[roll + bonus] = final_rolls[roll + bonus] + (
                    prob * bonus_prob
                )
        final_rolls = {val + res_bonus: prob for val, prob in final_rolls.items()}
        x_data = [float(x) for x in final_rolls.keys()]
        y_data = [float(y) for y in final_rolls.values()]
        update_plot("roll1", "x_roll1", "y_roll1", x_data, y_data)
        show_item("roll1")
        exp = expected(final_rolls)
        sdev = standard_dev(final_rolls)
        set_value("exp1", f"Expected Value: {exp:0.2f}")
        set_value(
            "sdev1",
            f"Standard Deviation: {sdev:0.2f} ({exp - sdev:0.2f} - {exp + sdev:0.2f})",
        )
        min_rolls = {
            roll: sum(v for k, v in final_rolls.items() if k >= roll)
            for roll in final_rolls.keys()
        }
        x_data = [float(x) for x in min_rolls.keys()]
        y_data = [float(y) for y in min_rolls.values()]
        update_plot("roll2", "x_roll2", "y_roll2", x_data, y_data)
        show_item("roll2")
        mid = next(k for k, v in reversed(min_rolls.items()) if v >= 0.5)
        set_value("desc_min", f">= 50% chance of rolling at least {mid}")

    except Exception:
        hide_item("roll1")
        hide_item("roll2")
        print(traceback.format_exc())


def update_plot(
    plot: str, x_tag: str, y_tag: str, x_data: List[float], y_data: List[float]
):
    delete_item(y_tag)
    delete_item(x_tag)
    if does_alias_exist(y_tag):
        remove_alias(y_tag)
    if does_alias_exist(x_tag):
        remove_alias(x_tag)
    add_plot_axis(parent=plot, axis=mvXAxis, tag=x_tag)
    y_label = "Probability %"
    add_plot_axis(parent=plot, axis=mvYAxis, label=y_label, tag=y_tag)
    add_bar_series(x_data, y_data, parent=y_tag, weight=0.8)
    set_axis_limits(x_tag, ymin=min(x_data) - 0.8, ymax=max(x_data) + 0.8)
    set_axis_limits(y_tag, ymin=0.0, ymax=max(y_data) * 1.1)
    x_labels = [str(int(x)) for x in x_data]
    set_axis_ticks(x_tag, tuple(zip(x_labels, x_data)))
    y_labels = [f"{y:0.2%}" for y in y_data]
    set_axis_ticks(y_tag, tuple(zip(y_labels, y_data)))
    bind_item_theme(plot, "plot_theme")


def bar_plot(
    plot_tag: str,
    label: str,
    height: int,
    width: int,
    tag_x: str,
    tag_y: str,
    series: str,
):
    with plot(
        tag=plot_tag,
        label=label,
        height=height,
        width=width,
        no_mouse_pos=True,
    ):
        add_plot_axis(parent=plot_tag, axis=mvXAxis, tag=tag_x)
        y_label = "Probability %"
        add_plot_axis(parent=plot_tag, axis=mvYAxis, label=y_label, tag=tag_y)
        add_bar_series([0.0], [0.0], parent=tag_y, weight=0.8, tag=series)
        bind_item_theme(plot_tag, "plot_theme")
