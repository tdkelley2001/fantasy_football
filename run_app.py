"""Launch the React app and local Python API."""
from fantasy_projection.web_app import main
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="Start without opening a browser tab.")
    args = parser.parse_args()
    main(open_browser=not args.no_browser)
