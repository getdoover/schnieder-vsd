"""Schneider VSD Control Application."""

from pydoover.docker import run_app

from .application import SchneiderVsdApplication


def main():
    run_app(SchneiderVsdApplication())
