"""ue-eyes CLI entry point."""

import click


@click.group()
@click.version_option()
def main() -> None:
    """Give AI agents visual access to Unreal Engine 5.7 projects."""


if __name__ == "__main__":
    main()
