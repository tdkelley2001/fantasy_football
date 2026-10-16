"""Ask the running local app to shut down, without killing unrelated processes."""
import json
from urllib.error import URLError
from urllib.request import Request, ProxyHandler, build_opener


def stop_app(url="http://127.0.0.1:8502"):
    # A machine's HTTP proxy should never handle this local control request.
    client = build_opener(ProxyHandler({}))
    try:
        with client.open(url + "/api/lifecycle", timeout=5) as response:
            identity = json.load(response)
        if not isinstance(identity, dict) or identity.get("application") != "fantasy-football-studio":
            print("The service on port 8502 is not Fantasy Football Studio; nothing was stopped.")
            return 1
        request = Request(url + "/api/shutdown", data=b"{}", headers={
            "Content-Type": "application/json", "X-Studio-Control": "shutdown",
        }, method="POST")
        with client.open(request, timeout=5) as response:
            result = json.load(response)
        if not isinstance(result, dict) or result.get("application") != "fantasy-football-studio" or result.get("stopping") is not True:
            print("The app did not confirm shutdown.")
            return 1
    except (URLError, OSError, ValueError):
        print("Could not reach a compatible app. It may already be stopped; older versions need one manual restart.")
        return 1
    print("Shutdown requested. The app will exit; in-progress analyses are discarded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(stop_app())
