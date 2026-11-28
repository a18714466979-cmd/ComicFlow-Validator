"""Print the installed application's name and version."""

if __package__:
    from .brand import APP_NAME_EN, APP_NAME_ZH, VERSION
else:
    from brand import APP_NAME_EN, APP_NAME_ZH, VERSION


def main():
    print(f"{APP_NAME_ZH} · {APP_NAME_EN} v{VERSION}")


if __name__ == "__main__":
    main()
