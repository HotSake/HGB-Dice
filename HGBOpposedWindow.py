from decimal import Decimal
from operator import attrgetter
from typing import Dict
from dearpygui.dearpygui import *
from functools import partial
import HGBModelDefs as md
import HGBWeaponDefs as wd
import HGBRules as hgb
from itertools import chain
import HGBDiceStats as stats
import traceback

WINDOW_WIDTH, WINDOW_HEIGHT = 1350, 950
TRAIT_LIST_WIDTH = 200
SMALL_INPUT_WIDTH = 50
PLOT_HEIGHT = 450
PLOT_WIDTH = 425
OPP_WINDOW = "opp_setup_window"

# TODO Add rerolls

HIDE_TRAITS = []

att_traits: List[Dict[str, Any]] = []
wpn_traits: List[Dict[str, Any]] = []
def_traits: List[Dict[str, Any]] = []
avail_traits: List[str] = []
selected_traits: List[Dict[str, Any]] = []
tests: int = 0

modal_window = partial(window, modal=True, no_resize=True, no_move=True, no_close=True)


def build_traits():
    global selected_traits, avail_traits
    trait_role = get_value("trait_role")
    if trait_role == "att":
        selected_traits = att_traits
        trait_defs = md.MODEL_TRAIT_DEFS
        avail_traits = [k for k, v in trait_defs.items() if "att" in v.valid_role]
    elif trait_role == "wpn":
        selected_traits = wpn_traits
        trait_defs = wd.WEAPON_TRAIT_DEFS
        avail_traits = [k for k, v in trait_defs.items() if v.valid_role]
    elif trait_role == "def":
        selected_traits = def_traits
        trait_defs = md.MODEL_TRAIT_DEFS
        avail_traits = [k for k, v in trait_defs.items() if "def" in v.valid_role]

    block_traits = []
    excluded_traits = list(
        chain.from_iterable(
            trait_defs[name].excludes for name in [t["name"] for t in selected_traits]
        )
    )
    missing_required = [
        t
        for t in avail_traits
        if not set(trait_defs[t].requires).issubset(
            set(s["name"] for s in selected_traits)
        )
    ]
    avail_traits = [
        t
        for t in avail_traits
        if t
        not in chain(
            HIDE_TRAITS,
            block_traits,
            excluded_traits,
            missing_required,
            [t["name"] for t in selected_traits],
        )
    ]

    configure_item(
        "selected_traits",
        items=sorted([" ".join(map(str, t.values())) for t in selected_traits]),
    )
    configure_item("selected_traits", num_items=len(selected_traits))
    configure_item(
        "selected_traits", callback=remove_trait_cb(selected_traits, trait_defs)
    )
    configure_item("available_traits", items=sorted(avail_traits))
    configure_item("available_traits", num_items=len(avail_traits))
    configure_item(
        "available_traits", callback=configure_trait(selected_traits, trait_defs)
    )


def configure_trait(selected_traits, trait_defs: Dict[str, hgb.Trait]):
    def callback():
        nonlocal trait_defs, selected_traits
        name = get_value(item="available_traits")
        trait = trait_defs[name]

        if "value" in trait.required_params:

            def close_callback():
                selected_traits.append(
                    {"name": name, "value": int(get_value(item="trait_value"))}
                )
                for t in trait_defs[name].excludes:
                    remove_trait(
                        trait_list=selected_traits, trait_defs=trait_defs, name=t
                    )
                hide_item("value_popup")
                build_traits()

            def allow_done():
                if get_value(item="trait_value").isdigit():
                    configure_item("value_done", show=True)
                else:
                    configure_item("value_done", show=False)

            set_value("trait_value", "")
            hide_item("value_done")
            configure_item("trait_value", callback=allow_done)
            configure_item("value_done", callback=close_callback)
            show_item("value_popup")
        else:
            selected_traits.append({"name": name})
            for t in trait_defs[name].excludes:
                remove_trait(trait_list=selected_traits, trait_defs=trait_defs, name=t)
            build_traits()

    return callback


def remove_trait_cb(selected_traits, trait_defs: Dict[str, hgb.Trait]) -> Callable:
    def callback():
        nonlocal trait_defs, selected_traits
        trait = get_value("selected_traits")
        name = str(trait).split()[0]
        remove_trait(trait_list=selected_traits, trait_defs=trait_defs, name=name)
        build_traits()

    return callback


def remove_trait(trait_list: List[Dict], trait_defs: Dict[str, hgb.Trait], name: str):
    indices = [i for i, v in enumerate(trait_list) if v["name"] == name]
    if not indices:
        return None
    trait_list.pop(indices.pop())
    removes = [t["name"] for t in trait_list if name in trait_defs[t["name"]].requires]
    for tn in removes:
        remove_trait(trait_list=trait_list, trait_defs=trait_defs, name=tn)


def pick_traits(sender, app_data):
    """Show the trait picker with the available and selected traits of the desired type.
    Configure list validation and updating accordingly.
    """

    if sender == "btn_att_traits":
        set_value("trait_role", "att")
    elif sender == "btn_wpn_traits":
        set_value("trait_role", "wpn")
    elif sender == "btn_def_traits":
        set_value("trait_role", "def")

    build_traits()
    show_item("trait_picker")


def update_traits():
    configure_item(
        "lst_att_traits",
        items=sorted([" ".join(map(str, t.values())) for t in att_traits]),
    )
    configure_item(
        "lst_wpn_traits",
        items=sorted([" ".join(map(str, t.values())) for t in wpn_traits]),
    )
    configure_item(
        "lst_def_traits",
        items=sorted([" ".join(map(str, t.values())) for t in def_traits]),
    )
    if "ANN" in (t["name"] for t in att_traits):
        show_item("att_ann")
    else:
        set_value("att_ann", False)
        hide_item("att_ann")

    if "ANN" in (t["name"] for t in def_traits):
        show_item("def_ann")
    else:
        set_value("def_ann", False)
        hide_item("def_ann")

    update_test()
    hide_item("trait_picker")


def att_method_cb():
    if get_value("att_method") == "Melee":
        set_value("att_range", "Optimal")

    if get_value("att_method") == "Indirect":
        enable_item("att_fire_mission")
        set_value("att_focus", False)
        disable_item("att_focus")
    else:
        disable_item("att_fire_mission")
        set_value("att_fire_mission", False)
        enable_item("att_focus")

    fire_mission_cb()


def fire_mission_cb():
    if not get_value("att_fire_mission"):
        set_value("att_TD", False)
        disable_item("att_TD")
        enable_item("att_AE_secondary")
    else:
        enable_item("att_TD")
        set_value("att_AE_secondary", False)

    update_test()


def ae_secondary_cb():
    if get_value("att_AE_secondary"):
        set_value("att_fire_mission", False)
        fire_mission_cb()

    update_test()


def crippled_cb(model: str) -> Callable:
    def callback():
        nonlocal model
        if get_value(f"{model}_crippled"):
            if get_value(f"{model}_speed") == "Top":
                set_value(f"{model}_speed", "Combat")
            configure_item(
                f"{model}_speed",
                items=list(speed.name for speed in hgb.Speed if speed.name != "Top"),
            )
        else:
            configure_item(
                f"{model}_speed",
                items=list(speed.name for speed in hgb.Speed),
            )

        update_test()

    return callback


def make_opp_window():

    with modal_window(
        tag="value_popup",
        show=False,
        width=150,
        height=25,
    ):
        with group(horizontal=True):
            add_text("Enter Value")
            add_input_text(
                tag="trait_value",
                width=SMALL_INPUT_WIDTH,
                default_value=1,
            )

        add_button(
            tag="value_done",
            label="Done",
            show=False,
        )

    with window(
        tag="trait_picker",
        label="Choose Traits",
        show=False,
        width=400,
        height=600,
    ):
        add_text("", tag="trait_role", show=False)
        with group(horizontal=True):
            with group():
                add_text("Available Traits")
                add_listbox(
                    tag="available_traits",
                    width=TRAIT_LIST_WIDTH,
                )

            with group():
                add_text("Selected Traits")
                add_listbox(tag="selected_traits", width=TRAIT_LIST_WIDTH)
                add_button(
                    label="Done",
                    callback=update_traits,
                )

    with window(
        label="Attack Scenario",
        tag=OPP_WINDOW,
        height=WINDOW_HEIGHT,
        width=WINDOW_WIDTH,
        horizontal_scrollbar=True,
        no_scrollbar=False,
    ):
        with table(
            header_row=False,
            resizable=False,
            policy=mvTable_SizingStretchProp,
            borders_outerH=False,
            borders_outerV=False,
            borders_innerH=False,
            borders_innerV=True,
        ):
            for _ in range(3):
                add_table_column(
                    width_stretch=True,
                    no_resize=True,
                    no_reorder=True,
                    no_sort=True,
                )
            with table_row():
                with table_cell():
                    add_text("Attacker", tag="att_label")
                    with group(horizontal=True):
                        add_text("Skill:")
                        add_input_text(
                            tag="att_skill",
                            width=SMALL_INPUT_WIDTH,
                            default_value=4,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Speed:")
                        add_combo(
                            tag="att_speed",
                            items=list(speed.name for speed in hgb.Speed),
                            width=TRAIT_LIST_WIDTH,
                            default_value="Combat",
                            callback=update_test,
                        )
                    add_checkbox(
                        label="Crippled/Haywired",
                        tag="att_crippled",
                        callback=crippled_cb(model="att"),
                    )
                    add_checkbox(
                        label="ANN active",
                        tag="att_ann",
                        callback=update_test,
                        show=False,
                    )
                    add_text("Traits")
                    with group(horizontal=True):
                        add_listbox(tag="lst_att_traits", width=TRAIT_LIST_WIDTH)
                        add_button(
                            tag="btn_att_traits",
                            label="Config",
                            callback=pick_traits,
                        )
                    add_text("Weapon")
                    with group(horizontal=True):
                        add_text("Damage:")
                        add_input_text(
                            tag="wpn_damage",
                            width=SMALL_INPUT_WIDTH,
                            default_value=6,
                            callback=update_test,
                        )
                    add_text("Traits")
                    with group(horizontal=True):
                        add_listbox(tag="lst_wpn_traits", width=TRAIT_LIST_WIDTH)
                        add_button(
                            tag="btn_wpn_traits",
                            label="Config",
                            callback=pick_traits,
                        )
                    with group(horizontal=True):
                        add_text("Custom dice mod:")
                        add_input_text(
                            tag="att_dice_mod",
                            width=SMALL_INPUT_WIDTH,
                            default_value=0,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Custom result mod:")
                        add_input_text(
                            tag="att_result_mod",
                            width=SMALL_INPUT_WIDTH,
                            default_value=0,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Custom threshold mod:")
                        add_input_text(
                            tag="att_threshold_mod",
                            width=SMALL_INPUT_WIDTH,
                            default_value=0,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Reroll if:")
                        add_combo(
                            tag="att_reroll",
                            items=list(rule.name for rule in hgb.RerollRules),
                            width=TRAIT_LIST_WIDTH,
                            default_value="Never",
                        )

                with table_cell():
                    add_text("Attack Parameters", tag="param_label")
                    with group(horizontal=True):
                        add_text("Attack Type:")
                        add_combo(
                            tag="att_method",
                            items=list(method.name for method in hgb.AttackMethods),
                            width=TRAIT_LIST_WIDTH,
                            default_value="Direct",
                            callback=att_method_cb,
                        )
                    add_checkbox(
                        label="Fire Mission",
                        tag="att_fire_mission",
                        callback=fire_mission_cb,
                        enabled=False,
                    )
                    add_checkbox(label="TD", tag="att_TD", callback=update_traits)
                    add_checkbox(label="Focus", tag="att_focus", callback=update_traits)
                    add_checkbox(
                        label="AE Secondary Target",
                        tag="att_AE_secondary",
                        callback=ae_secondary_cb,
                    )
                    with group(horizontal=True):
                        add_text("Attack Range:", tag="range_label")
                        add_combo(
                            tag="att_range",
                            items=list(range.name for range in hgb.Ranges),
                            width=TRAIT_LIST_WIDTH,
                            default_value="Optimal",
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Facing:")
                        add_combo(
                            tag="def_facing",
                            items=list(facing.name for facing in hgb.Facings),
                            width=TRAIT_LIST_WIDTH,
                            default_value="Front",
                            callback=update_test,
                        )

                with table_cell():
                    add_text("Defender", tag="def_label")
                    with group(horizontal=True):
                        add_text("Skill:")
                        add_input_text(
                            tag="def_skill",
                            width=SMALL_INPUT_WIDTH,
                            default_value=4,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Model Type:")
                        add_combo(
                            tag="def_type",
                            items=list(mt.name for mt in hgb.ModelTypes),
                            width=TRAIT_LIST_WIDTH,
                            default_value="Gear",
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Speed:")
                        add_combo(
                            tag="def_speed",
                            items=list(speed.name for speed in hgb.Speed),
                            width=TRAIT_LIST_WIDTH,
                            default_value="Combat",
                            callback=update_test,
                        )
                    add_checkbox(
                        label="Crippled/Haywired",
                        tag="def_crippled",
                        callback=crippled_cb(model="def"),
                    )
                    add_checkbox(
                        label="ANN active",
                        tag="def_ann",
                        callback=update_test,
                        show=False,
                    )
                    with group(horizontal=True):
                        add_text("Armor:")
                        add_input_text(
                            tag="def_armor",
                            width=SMALL_INPUT_WIDTH,
                            default_value=6,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Hull:")
                        add_input_text(
                            tag="def_hull",
                            width=SMALL_INPUT_WIDTH,
                            default_value=4,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Structure:")
                        add_input_text(
                            tag="def_structure",
                            width=SMALL_INPUT_WIDTH,
                            default_value=2,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Cover:")
                        add_combo(
                            tag="def_cover",
                            items=list(cover.name for cover in hgb.CoverAmount),
                            width=TRAIT_LIST_WIDTH,
                            default_value="Open",
                            callback=update_test,
                        )
                    add_checkbox(label="Smoke", tag="def_smoke", callback=update_traits)
                    add_checkbox(
                        label="ECM Defense", tag="def_ECM", callback=update_traits
                    )
                    add_text("Traits")
                    with group(horizontal=True):
                        add_listbox(tag="lst_def_traits", width=TRAIT_LIST_WIDTH)
                        add_button(
                            tag="btn_def_traits",
                            label="Config",
                            callback=pick_traits,
                        )
                    with group(horizontal=True):
                        add_text("Custom dice mod:")
                        add_input_text(
                            tag="def_dice_mod",
                            width=SMALL_INPUT_WIDTH,
                            default_value=0,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Custom result mod:")
                        add_input_text(
                            tag="def_result_mod",
                            width=SMALL_INPUT_WIDTH,
                            default_value=0,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Custom threshold mod:")
                        add_input_text(
                            tag="def_threshold_mod",
                            width=SMALL_INPUT_WIDTH,
                            default_value=0,
                            callback=update_test,
                        )
                    with group(horizontal=True):
                        add_text("Reroll if:")
                        add_combo(
                            tag="def_reroll",
                            items=list(rule.name for rule in hgb.RerollRules),
                            width=TRAIT_LIST_WIDTH,
                            default_value="Never",
                        )

            with table_row():
                add_button(tag="btn_run", label="Run", callback=run_test)

        update_test()

    with theme(tag="plot_theme"):
        with theme_component(mvBarSeries):
            add_theme_color(mvPlotCol_Line, (0, 0, 0), category=mvThemeCat_Plots)
            add_theme_style(mvPlotStyleVar_LineWeight, 3, category=mvThemeCat_Plots)


def make_scenario() -> hgb.Scenario:
    att_specials = [
        {
            "name": "Speed",
            "speed": hgb.Speed[get_value("att_speed")],
        },
        {"name": "Skill", "value": Decimal(get_value("att_skill"))},
        {"name": "Facing", "facing": hgb.Facings[get_value("def_facing")]},
        {"name": "CustomDice", "value": Decimal(get_value("att_dice_mod"))},
        {"name": "CustomResult", "value": Decimal(get_value("att_result_mod"))},
        {"name": "CustomThreshold", "value": Decimal(get_value("att_threshold_mod"))},
        {"name": "Reroll", "rule": hgb.RerollRules[get_value("att_reroll")]},
    ]

    att_final_traits = [t for t in att_traits]
    if get_value("att_crippled"):
        att_specials.append({"name": "Crippled"})
    if "ElevatedVTOL" in (t["name"] for t in att_traits):
        att_specials.append({"name": "Elevated"})
    if "ANN" in (t["name"] for t in att_traits) and not get_value("att_ann"):
        att_final_traits = [t for t in att_final_traits if t["name"] != "ANN"]

    wpn_specials = [
        {"name": "Damage", "value": Decimal(get_value("wpn_damage")), "source": "DAM"},
        {"name": "Method", "method": hgb.AttackMethods[get_value("att_method")]},
    ]
    wpn_specials.append({"name": "Range", "range": hgb.Ranges[get_value("att_range")]})
    if get_value("att_fire_mission"):
        wpn_specials.append({"name": "FireMission"})
    if get_value("att_TD"):
        wpn_specials.append({"name": "TD"})
    if get_value("att_focus"):
        wpn_specials.append({"name": "Focus"})
    if get_value("att_AE_secondary"):
        wpn_specials.append({"name": "AESecondary"})

    attacker = hgb.make_model(
        role=hgb.Roles.Attacker,
        weapon_components=wd.make_weapon_components(wpn_traits + wpn_specials),
        model_components=md.make_model_components(att_final_traits + att_specials),
    )

    def_specials = [
        {"name": "Skill", "value": Decimal(get_value("def_skill"))},
        {
            "name": "Speed",
            "speed": hgb.Speed[get_value("def_speed")],
        },
        {"name": "Armor", "value": Decimal(get_value("def_armor"))},
        {"name": "Hull", "value": Decimal(get_value("def_hull"))},
        {"name": "Structure", "value": Decimal(get_value("def_structure"))},
        {"name": get_value("def_type")},
        {"name": "CustomDice", "value": Decimal(get_value("def_dice_mod"))},
        {"name": "CustomResult", "value": Decimal(get_value("def_result_mod"))},
        {"name": "CustomThreshold", "value": Decimal(get_value("def_threshold_mod"))},
        {"name": "Cover", "amount": hgb.CoverAmount[get_value("def_cover")]},
        {"name": "Reroll", "rule": hgb.RerollRules[get_value("def_reroll")]},
    ]
    def_final_traits = [t for t in def_traits]
    if "ANN" in (t["name"] for t in def_traits) and not get_value("def_ann"):
        def_final_traits = [t for t in def_final_traits if t["name"] != "ANN"]

    if get_value("def_smoke"):
        def_specials.append({"name": "Smoke"})
    if get_value("def_ECM"):
        def_specials.append({"name": "ECMDefense"})
    if get_value("def_crippled"):
        def_specials.append({"name": "Crippled"})

    defender = hgb.make_model(
        role=hgb.Roles.Defender,
        model_components=md.make_model_components(def_final_traits + def_specials),
    )

    return hgb.Scenario(attacker=attacker, defender=defender)


def update_test() -> bool:
    try:
        test = make_scenario()
        rolls = test.describe_rolls()
        set_value("att_label", f"Attacker: {rolls['attacker']}")
        set_value("def_label", f"Defender: {rolls['defender']}")

    except Exception:
        print(traceback.format_exc())


def run_test():
    try:
        test_outcomes = list(sorted(make_scenario().evaluate(), key=attrgetter("prob")))

        analyses = dict()
        analyses.update(stats.BASIC_ANALYSES)
        analyses.update(stats.STATUS_ANALYSES)
        results = [stats.do_analysis(test_outcomes, an) for an in analyses.values()]
        results = [r for r in results if r is not None]

        global tests
        tests += 1

        # print_results(results)
        graph_results(test_num=tests, results=results, analyses=analyses)
    except Exception:
        print(traceback.format_exc())


def show_plots(show: Tuple[str], hide: Tuple[str]):
    def callback():
        nonlocal show, hide
        for tag in hide:
            hide_item(tag)
        for tag in show:
            show_item(tag)

    return callback


def graph_results(
    test_num: int, results: List[Dict], analyses: Dict[str, stats.Analysis]
):
    with window(
        label=f"Test {test_num:g}",
        height=WINDOW_HEIGHT - 20 * test_num,
        width=WINDOW_WIDTH,
        no_scrollbar=False,
        horizontal_scrollbar=True,
        pos=(0, 20 + (20 * test_num)),
    ):
        add_text("Click plots to cycle between analysis types!")
        cols = max(len(res.get("by_source", [])) for res in results) + 1
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
            for res in results:
                datatype = analyses[res["name"]].datatype
                if datatype == stats.AnalysisType.BOOL:
                    avg = f"{res['average']:0.1%}"
                    norm_label = (
                        f"WHEN {res['name']} is True"
                        + f" (Avg: {res['normalized_average']:0.1%})"
                    )
                else:
                    avg = f"{res['average']:0.2f}"
                    norm_label = (
                        f"WHEN {res['name']} > 0"
                        + f" (Avg: {res['normalized_average']:0.2f})"
                    )
                min_label = f"{res['name']} AT LEAST X:"

                base_tags = []
                normal_tags = []
                min_tags = []
                with table_row(height=PLOT_HEIGHT + 5):
                    plot_tag = f"plot_{test_num}_{res['name']}"
                    norm_tag = plot_tag + "_norm"
                    min_tag = plot_tag + "_min"
                    base_tags.append(plot_tag)
                    normal_tags.append(norm_tag)
                    min_totals = res.get("min_totals", [])
                    if min_totals:
                        min_tags.append(min_tag)
                    with table_cell():
                        bar_plot(
                            plot_tag=plot_tag,
                            label=f"{res['name']} (Avg: {avg})",
                            height=PLOT_HEIGHT,
                            width=PLOT_WIDTH,
                            data_x=[float(k) for k in res["totals"].keys()],
                            data_y=[float(v) for v in res["totals"].values()],
                            tag_x=f"x_{test_num}_{res['name']}",
                            tag_y=f"y_{test_num}_{res['name']}",
                            datatype=datatype,
                        )
                        bar_plot(
                            plot_tag=norm_tag,
                            label=norm_label,
                            height=PLOT_HEIGHT,
                            width=PLOT_WIDTH,
                            data_x=[float(k) for k in res["normalized_totals"].keys()],
                            data_y=[
                                float(v) for v in res["normalized_totals"].values()
                            ],
                            tag_x=f"x_{test_num}_{res['name']}_norm",
                            tag_y=f"y_{test_num}_{res['name']}_norm",
                            datatype=datatype,
                        )
                        if min_totals:
                            bar_plot(
                                plot_tag=min_tag,
                                label=min_label,
                                height=PLOT_HEIGHT,
                                width=PLOT_WIDTH,
                                data_x=[float(k) for k in min_totals.keys()],
                                data_y=[float(v) for v in min_totals.values()],
                                tag_x=f"x_{test_num}_{res['name']}_min",
                                tag_y=f"y_{test_num}_{res['name']}_min",
                                datatype=datatype,
                            )

                    sources = res.get("by_source", [])
                    for source in sources:
                        plot_tag = f"plot_{test_num}_{res['name']}_{source['name']}"
                        norm_tag = plot_tag + "_norm"
                        min_tag = plot_tag + "_min"
                        base_tags.append(plot_tag)
                        normal_tags.append(norm_tag)
                        min_totals = source.get("min_totals", [])
                        if min_totals:
                            min_tags.append(min_tag)
                        if datatype == stats.AnalysisType.BOOL:
                            avg = f"{source['average']:0.1%}"
                            norm_label = (
                                f"WHEN {res['name']} is True:"
                                + f"\n{res['name']} from {source['name']}"
                                + f" (Avg: {source['normalized_average']:0.1%})"
                            )
                        else:
                            avg = f"{source['average']:0.2f}"
                            norm_label = (
                                f"WHEN {res['name']} > 0:"
                                + f"\n{res['name']} from {source['name']}"
                                + f" (Avg: {source['normalized_average']:0.2f})"
                            )
                        min_label = (
                            f"{res['name']} AT LEAST X:"
                            + f"\n{res['name']} from {source['name']}"
                        )
                        with table_cell():
                            bar_plot(
                                plot_tag=plot_tag,
                                label=f"{res['name']} from {source['name']} (Avg: {avg})",
                                height=PLOT_HEIGHT,
                                width=PLOT_WIDTH,
                                data_x=[float(k) for k in source["totals"].keys()],
                                data_y=[float(v) for v in source["totals"].values()],
                                tag_x=f"x_{test_num}_{res['name']}_{source['name']}",
                                tag_y=f"y_{test_num}_{res['name']}_{source['name']}",
                                datatype=datatype,
                            )
                            bar_plot(
                                plot_tag=norm_tag,
                                label=norm_label,
                                height=PLOT_HEIGHT,
                                width=PLOT_WIDTH,
                                data_x=[
                                    float(k) for k in source["normalized_totals"].keys()
                                ],
                                data_y=[
                                    float(v)
                                    for v in source["normalized_totals"].values()
                                ],
                                tag_x=f"x_{test_num}_{res['name']}_{source['name']}_norm",
                                tag_y=f"y_{test_num}_{res['name']}_{source['name']}_norm",
                                datatype=datatype,
                            )
                            if min_totals:
                                bar_plot(
                                    plot_tag=min_tag,
                                    label=min_label,
                                    height=PLOT_HEIGHT,
                                    width=PLOT_WIDTH,
                                    data_x=[float(k) for k in min_totals.keys()],
                                    data_y=[float(v) for v in min_totals.values()],
                                    tag_x=f"x_{test_num}_{res['name']}_{source['name']}_min",
                                    tag_y=f"y_{test_num}_{res['name']}_{source['name']}_min",
                                    datatype=datatype,
                                )

                base_handler_tag = f"handler_base_{test_num}_{res['name']}"
                normal_handler_tag = f"handler_normal_{test_num}_{res['name']}"
                min_handler_tag = f"handler_min_{test_num}_{res['name']}"

                with item_handler_registry(tag=base_handler_tag):
                    add_item_clicked_handler(
                        callback=show_plots(
                            tuple(normal_tags), tuple(base_tags + min_tags)
                        )
                    )

                with item_handler_registry(tag=normal_handler_tag):
                    if min_tags:
                        show = min_tags
                        hide = base_tags + normal_tags
                    else:
                        show = base_tags
                        hide = normal_tags
                    add_item_clicked_handler(
                        callback=show_plots(tuple(show), tuple(hide))
                    )

                with item_handler_registry(tag=min_handler_tag):
                    add_item_clicked_handler(
                        callback=show_plots(
                            tuple(base_tags), tuple(normal_tags + min_tags)
                        )
                    )

                for tag in base_tags:
                    bind_item_handler_registry(tag, base_handler_tag)
                for tag in normal_tags:
                    bind_item_handler_registry(tag, normal_handler_tag)
                for tag in min_tags:
                    bind_item_handler_registry(tag, min_handler_tag)

                show_plots(tuple(base_tags), tuple(normal_tags + min_tags))()


def bar_plot(
    plot_tag: str,
    label: str,
    height: int,
    width: int,
    data_x: List[float],
    data_y: List[float],
    tag_x: str,
    tag_y: str,
    datatype: stats.AnalysisType,
):
    with plot(
        tag=plot_tag,
        label=label,
        height=height,
        width=width,
        no_mouse_pos=True,
    ):
        add_plot_axis(parent=plot_tag, axis=mvXAxis, tag=tag_x)
        if datatype == stats.AnalysisType.BOOL:
            set_axis_ticks(tag_x, (("No", 0), ("Yes", 1)))
        elif datatype == stats.AnalysisType.RANGE:
            labels = [str(int(x)) for x in data_x]
            set_axis_ticks(tag_x, tuple(zip(labels, data_x)))
        y_label = "Probability %"
        add_plot_axis(parent=plot_tag, axis=mvYAxis, label=y_label, tag=tag_y)
        labels = [f"{y:0.2%}" for y in data_y]
        set_axis_ticks(tag_y, tuple(zip(labels, data_y)))
        add_bar_series(data_x, data_y, parent=tag_y, weight=0.8)
        set_axis_limits(tag_x, ymin=min(data_x) - 0.8, ymax=max(data_x) + 0.8)
        set_axis_limits(tag_y, ymin=0.0, ymax=max(data_y) * 1.1)
        bind_item_theme(plot_tag, "plot_theme")


def print_results(results: List[Dict]):
    for res in results:
        print(f"{res['name']} (Avg: {res['average']:0.2f})")
        print("\n".join(f"\t{k:g}: {v:0.2%}" for k, v in res["totals"].items()))
        sources = res.get("by_source", [])
        for source in sources:
            print(f"\n\t{source['name']} (Avg: {source['average']:0.2g})")
            print(
                "\n".join(f"\t\t{k:g}: {v:0.2%}" for k, v in source["totals"].items())
            )
