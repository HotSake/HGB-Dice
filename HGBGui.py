from decimal import getcontext
from dearpygui.dearpygui import *
from HGBOpposedWindow import OPP_SETUP_WINDOW, make_opp_window
from HGBUnopposedWindow import UNOPP_SETUP_WINDOW, make_unopp_window
from HGBGuiConstants import *

# TODO: Associate model params w/ objects
# TODO: Save/load config


getcontext().prec = 12


def opposed_cb():
    show_item(OPP_SETUP_WINDOW)
    hide_item(UNOPP_SETUP_WINDOW)


def unopposed_cb():
    hide_item(OPP_SETUP_WINDOW)
    show_item(UNOPP_SETUP_WINDOW)


def start_gui():
    create_context()
    create_viewport(
        title="Heavy Gear Blitz Dice Stats",
        width=VIEWPORT_WIDTH,
        height=VIEWPORT_HEIGHT,
    )
    with viewport_menu_bar():
        with menu(label="Mode"):
            add_menu_item(label="Independent Roll", callback=unopposed_cb)
            add_menu_item(label="Opposed Roll", callback=opposed_cb)

    make_opp_window()
    make_unopp_window()
    opposed_cb()

    setup_dearpygui()
    show_viewport()
    show_item_registry()
    # show_style_editor()
    # show_documentation()
    start_dearpygui()
    destroy_context()


if __name__ == "__main__":
    start_gui()
