import os

import pytest

DATABASE_URL = os.environ.get("VIDGEN_DATABASE_URL")
REDIS_URL = os.environ.get("VIDGEN_REDIS_URL")

requires_services = pytest.mark.skipif(
    not (DATABASE_URL and REDIS_URL),
    reason="set VIDGEN_DATABASE_URL and VIDGEN_REDIS_URL to run integration tests",
)
