import pytest

from oppie.plan import PlanEngine
from oppie.providers.local import LocalProvider
from tests.helpers import setup_instance


@pytest.fixture
def plan_engine(tmp_path):
    home = setup_instance(tmp_path)
    provider = LocalProvider(home)
    engine = PlanEngine(home, provider)
    yield engine
    provider.close()
