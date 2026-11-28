"""Contextual help entry shared by embedded and native project tools."""

from tkinter import ttk
from weakref import WeakSet

from .ui_language import translate


def guide_button(parent, topic, *, name="page_help"):
    root = parent._root()
    open_help = getattr(root, "open_storyboard_help", None)
    if open_help is None:
        return None
    caption = "导演台使用教程" if name == "director_help" else "本页帮助"
    button = ttk.Button(parent, name=name, text=translate(parent, caption),
                        command=lambda: open_help(topic() if callable(topic) else topic, source=parent),
                        style="Workbench.TButton")
    if not hasattr(root, "_guide_buttons"):
        root._guide_buttons = WeakSet()
    root._guide_buttons.add(button)
    button.guide_caption = caption

    def refresh(_event=None):
        button.configure(text=translate(parent, caption))

    button.bind("<Map>", refresh, add="+")
    button.bind("<Destroy>", lambda event: root._guide_buttons.discard(button)
                if event.widget is button else None, add="+")
    return button


def refresh_guide_buttons(root):
    for button in tuple(getattr(root, "_guide_buttons", ())):
        button.configure(text=translate(root, button.guide_caption))
