import json

import pytest

import oppie
from oppie.config import InstanceType
from oppie.instance import INSTANCE_DIRS, MARKER_FILENAME, Instance


def test_create_repo_instance(tmp_path):
    home = tmp_path / '.oppie'
    instance = Instance.create(home=home, instance_type=InstanceType.REPO)

    assert instance.home == home.resolve()
    assert instance.marker.instance_type == InstanceType.REPO
    assert instance.config is None
    assert (home / MARKER_FILENAME).exists()


def test_create_portfolio_instance(tmp_path):
    home = tmp_path / 'portfolio'
    instance = Instance.create(home=home, instance_type=InstanceType.PORTFOLIO)

    assert instance.marker.instance_type == InstanceType.PORTFOLIO


def test_create_all_directories(tmp_path):
    home = tmp_path / '.oppie'
    Instance.create(home=home, instance_type=InstanceType.REPO)

    for d in INSTANCE_DIRS:
        assert (home / d).is_dir(), f'Missing directory: {d}'


def test_create_marker_content(tmp_path):
    home = tmp_path / '.oppie'
    Instance.create(home=home, instance_type=InstanceType.REPO)
    data = json.loads((home / MARKER_FILENAME).read_text())

    assert data['version'] == oppie.__version__
    assert data['instance_type'] == 'repo'


def test_create_already_exists(tmp_path):
    home = tmp_path / '.oppie'
    Instance.create(home=home, instance_type=InstanceType.REPO)

    with pytest.raises(FileExistsError, match='already exists'):
        Instance.create(home=home, instance_type=InstanceType.REPO)


def test_create_config_is_none(tmp_path):
    home = tmp_path / '.oppie'
    instance = Instance.create(home=home, instance_type=InstanceType.REPO)

    assert instance.config is None
