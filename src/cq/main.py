"""This module provides the entry point for the application. It defines a `main` function that handles initialization, command-line argument parsing, and triggers the core application workflow. The module can be executed directly to run the application."""

from cq.cli import app


def main():
    """Runs the application."""
    app()


if __name__ == "__main__":
    main()
