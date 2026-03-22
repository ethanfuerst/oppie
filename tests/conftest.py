import pytest

from oppie.providers.local import LocalProvider
from tests.helpers import setup_instance


@pytest.fixture
def home(tmp_path):
    return setup_instance(tmp_path)


@pytest.fixture
def provider(home):
    provider = LocalProvider(home)
    yield provider
    provider.close()
