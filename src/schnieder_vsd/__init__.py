from pydoover.docker import run_app

from .application import SchniederVsdApplication
from .app_config import SchniederVsdConfig

def main():
    """
    Run the application.
    """
    run_app(SchniederVsdApplication(config=SchniederVsdConfig()))
