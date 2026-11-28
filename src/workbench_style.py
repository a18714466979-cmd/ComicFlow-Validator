"""Warm, shared desktop styling for the ComicFlow workbench."""

from tkinter import font, ttk


BACKGROUND = "#f8f5ef"
SURFACE = "#fffdfa"
INK = "#30271f"
MUTED = "#62564b"
LINE = "#e2d8cd"
TINT = "#f4e6db"
ACCENT = "#93432e"
ACCENT_HOVER = "#793725"
GREEN = "#42634a"
AMBER = "#815019"
SUBTLE = "#f1ebe3"
DISABLED = "#76695e"


def configure_workbench(window):
    styles = ttk.Style(window)
    if styles.theme_use() != "clam":
        styles.theme_use("clam")

    window.configure(background=BACKGROUND)
    styles.configure("TFrame", background=BACKGROUND)
    styles.configure("TLabel", background=BACKGROUND, foreground=INK)
    styles.configure("TLabelframe", background=BACKGROUND, bordercolor=LINE)
    styles.configure("TLabelframe.Label", background=BACKGROUND, foreground=INK)
    styles.configure("TSeparator", background=LINE)
    for name in ("TCheckbutton", "TRadiobutton"):
        styles.configure(name, background=BACKGROUND, foreground=INK)
        styles.map(name, background=[("active", TINT)], foreground=[("disabled", DISABLED)])

    styles.configure("TButton", background=SURFACE, foreground=INK, bordercolor=LINE,
                     lightcolor=SURFACE, darkcolor=SURFACE)
    styles.map("TButton", background=[("disabled", SUBTLE), ("pressed", TINT), ("active", TINT)],
               bordercolor=[("focus", ACCENT), ("active", ACCENT)],
               foreground=[("disabled", DISABLED)])
    styles.configure("Workbench.TButton", padding=(11, 7))
    styles.configure("Primary.Workbench.TButton", padding=(13, 7), background=ACCENT,
                     foreground="white", bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
    styles.map("Primary.Workbench.TButton", background=[("disabled", SUBTLE), ("pressed", ACCENT_HOVER),
                                                         ("active", ACCENT_HOVER)],
               bordercolor=[("disabled", LINE), ("focus", INK), ("active", ACCENT_HOVER)],
               foreground=[("disabled", DISABLED), ("!disabled", "white")])

    for name in ("TNotebook", "A.TNotebook", "Navigation.TNotebook"):
        styles.configure(name, background=BACKGROUND, bordercolor=LINE, tabmargins=(0, 0, 0, 0))
        styles.configure(f"{name}.Tab", background=SUBTLE, foreground=MUTED,
                         bordercolor=LINE, padding=(10, 7))
        styles.map(f"{name}.Tab", background=[("selected", SURFACE), ("active", TINT)],
                   foreground=[("selected", ACCENT), ("disabled", DISABLED)])
    # The batch window presents five explicit navigation buttons over four notebook pages.
    styles.layout("A.Hidden.TNotebook.Tab", [])

    styles.configure("A.TFrame", background=BACKGROUND)
    styles.configure("A.Card.TFrame", background=SURFACE)
    styles.configure("A.TLabel", background=BACKGROUND, foreground=INK)
    styles.configure("A.Muted.TLabel", background=BACKGROUND, foreground=MUTED)
    styles.configure("A.Card.TLabel", background=SURFACE, foreground=INK)
    styles.configure("A.CardMuted.TLabel", background=SURFACE, foreground=MUTED)
    styles.configure("A.Step.TButton", padding=(10, 8), background=SURFACE, bordercolor=LINE)
    styles.configure("A.Current.Step.TButton", padding=(10, 8), background=TINT,
                     foreground=ACCENT_HOVER, bordercolor=ACCENT)
    styles.configure("A.Done.Step.TButton", padding=(10, 8), foreground=GREEN)
    row_height = font.nametofont("TkDefaultFont", root=window).metrics("linespace") + 11
    for name in ("Treeview", "A.Treeview"):
        styles.configure(name, background=SURFACE, fieldbackground=SURFACE, foreground=INK,
                         bordercolor=LINE, rowheight=row_height)
        styles.map(name, background=[("selected", TINT)], foreground=[("selected", INK)])
        heading = name + ".Heading"
        styles.configure(heading, background=SUBTLE, foreground=INK,
                         bordercolor=LINE, lightcolor=SUBTLE, darkcolor=SUBTLE, padding=(6, 4))
        styles.map(heading, background=[("active", TINT)])
    return styles
