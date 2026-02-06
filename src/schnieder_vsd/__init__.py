"""Schneider VSD Control Application.

A Doover device app for monitoring and controlling Schneider Altivar
Variable Speed Drives via Modbus TCP.
"""

from pydoover.docker import run_app

from .application import SchniederVsdApplication
from .app_config import SchniederVsdConfig


def main():
    """Run the Schneider VSD control application."""
    run_app(SchniederVsdApplication(config=SchniederVsdConfig()))
