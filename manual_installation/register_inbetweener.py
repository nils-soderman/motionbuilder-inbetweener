"""
Create a menu entry for the Inbetweener tool
"""

import pyfbsdk as fb

MENU_TITLE = "Inbetweener"
PARENT_MENU = "Animation"


def on_menu_activated(Menu: fb.FBGenericMenu, Event: fb.FBEventMenu):
    if Event.Name == MENU_TITLE:
        import motionbuilder_inbetweener
        motionbuilder_inbetweener.show_tool()


def does_menu_exist() -> bool:
    """
    Check if the menu already exists
    """
    menu_manager = fb.FBMenuManager()
    parent_menu = menu_manager.GetMenu(f"{PARENT_MENU}")

    item = parent_menu.GetFirstItem()
    while item is not None:
        if item.Caption == MENU_TITLE:
            return True
        item = parent_menu.GetNextItem(item)

    return False


def main():
    menu_manager = fb.FBMenuManager()
    parent_menu = menu_manager.GetMenu(PARENT_MENU)
    if parent_menu:
        menu_manager.InsertLast(PARENT_MENU, MENU_TITLE)
        parent_menu.OnMenuActivate.Add(on_menu_activated)


if __name__ == "builtins":
    main()

