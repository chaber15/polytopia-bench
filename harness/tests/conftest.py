import sys
import threading
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))

import pytest  # noqa: E402

from bridge import Bridge  # noqa: E402
from fake_server import make_server  # noqa: E402


@pytest.fixture
def server():
    srv = make_server(port=0, max_turns=30)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def bridge(server):
    # "localhost" on purpose: that is what the plugin and the spec use
    return Bridge(f"http://localhost:{server.server_port}", timeout=5)
