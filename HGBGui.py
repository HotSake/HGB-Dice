from decimal import getcontext
from dearpygui.dearpygui import *
from gui.HGBOpposedWindow import OPP_SETUP_WINDOW, make_opp_window
from gui.HGBUnopposedWindow import UNOPP_SETUP_WINDOW, make_unopp_window
from gui.HGBGuiConstants import *

# TODO: Associate model params w/ objects
# TODO: Save/load config

"""Show main GUI. Run this file to start the app.

App development notes:

This app makes use of Python's functools and itertools modules quite extensively.
If you're not familiar with them, or some basics of functional programming (mostly
the concepts of "currying" or partial function calls and the built-in map() function),
I recommend you read up on functools.partial and itertools.chain to familiarize
yourself.

It also makes use of mostly immutable objects during the evaluation process (see frozen 
dataclasses). When a State needs to change, it is actually copied into a new State 
object by the use of the dataclasses.replace function. Most collections are also 
frozensets, which are just immutable sets.

As for the GUI, I sincerely apologize. I don't know what I'm doing with GUI programming,
and I'm sure it's a complete mess.
"""

getcontext().prec = 12  # Decimal precision to use if not otherwise specified.


def opposed_cb():
    show_item(OPP_SETUP_WINDOW)
    hide_item(UNOPP_SETUP_WINDOW)


def unopposed_cb():
    hide_item(OPP_SETUP_WINDOW)
    show_item(UNOPP_SETUP_WINDOW)


def start_gui():
    """Start and stop the main GUI."""
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
    # show_item_registry()
    # show_style_editor()
    # show_documentation()
    start_dearpygui()
    destroy_context()


if __name__ == "__main__":
    start_gui()
