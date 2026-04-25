"""Smoke test: confirm the package installs and imports cleanly."""

from hindcast import __version__


def main() -> None:
    print(f"Hindcast {__version__} alive.")


if __name__ == "__main__":
    main()
