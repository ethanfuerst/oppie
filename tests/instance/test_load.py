import pytest

import oppie
from oppie.config import InstanceType, ProviderType
from oppie.instance import Instance
from tests.instance.conftest import write_minimal_config


def test_load_existing_instance(tmp_path):
    home = tmp_path / '.oppie'
    Instance.create(home=home, instance_type=InstanceType.REPO)
    write_minimal_config(home)
    instance = Instance.load(home)

    assert instance.marker.instance_type == InstanceType.REPO
    assert instance.config is not None
    assert instance.config.provider.provider_type == ProviderType.LOCAL


def test_load_without_config(tmp_path):
    home = tmp_path / '.oppie'
    Instance.create(home=home, instance_type=InstanceType.REPO)
    instance = Instance.load(home)

    assert instance.config is None
    assert instance.marker.version == oppie.__version__


def test_load_nonexistent_home(tmp_path):
    with pytest.raises(FileNotFoundError, match='Instance home not found'):
        Instance.load(tmp_path / 'nope')


def test_load_missing_marker(tmp_path):
    bare_home = tmp_path / '.oppie'
    bare_home.mkdir()

    with pytest.raises(FileNotFoundError, match='Marker file not found'):
        Instance.load(bare_home)
