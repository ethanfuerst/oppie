import json
from pathlib import Path

import pytest

import oppie
from oppie.config import InstanceType, ProviderType
from oppie.instance import (
    INSTANCE_DIRS,
    MARKER_FILENAME,
    Instance,
    Marker,
)

# --- Helper ---


def _write_minimal_config(home: Path) -> None:
    """Write a minimal valid oppie.yaml into an instance's config dir."""
    import yaml

    config_path = home / 'config' / 'oppie.yaml'
    with open(config_path, 'w') as f:
        yaml.dump({'instance_type': 'repo', 'provider': {'type': 'local'}}, f)


# --- Marker tests ---


def test_marker_to_dict():
    marker = Marker(version='0.0.1', instance_type=InstanceType.REPO)
    d = marker.to_dict()

    assert d == {'version': '0.0.1', 'instance_type': 'repo'}


def test_marker_from_dict():
    data = {'version': '0.0.1', 'instance_type': 'portfolio'}
    marker = Marker.from_dict(data)

    assert marker.version == '0.0.1'
    assert marker.instance_type == InstanceType.PORTFOLIO


def test_marker_write_and_read(tmp_path):
    path = tmp_path / '.oppie-marker'
    original = Marker(version='0.0.1', instance_type=InstanceType.REPO)
    original.write(path)
    loaded = Marker.read(path)

    assert loaded.version == original.version
    assert loaded.instance_type == original.instance_type


def test_marker_read_malformed(tmp_path):
    path = tmp_path / '.oppie-marker'
    path.write_text('not json {{{')

    with pytest.raises(ValueError, match='Malformed marker file'):
        Marker.read(path)


def test_marker_read_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match='Marker file not found'):
        Marker.read(tmp_path / '.oppie-marker')


# --- Instance.create tests ---


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


# --- Instance.load tests ---


def test_load_existing_instance(tmp_path):
    home = tmp_path / '.oppie'
    Instance.create(home=home, instance_type=InstanceType.REPO)
    _write_minimal_config(home)
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


# --- Instance.detect tests ---


def test_detect_explicit_home(tmp_path):
    home = tmp_path / '.oppie'
    Instance.create(home=home, instance_type=InstanceType.REPO)
    result = Instance.detect(home=home)

    assert result == home.resolve()


def test_detect_explicit_home_invalid(tmp_path):
    with pytest.raises(FileNotFoundError, match='No valid instance'):
        Instance.detect(home=tmp_path / 'nope')


def test_detect_oppie_home_env_var(tmp_path, monkeypatch):
    home = tmp_path / '.oppie'
    Instance.create(home=home, instance_type=InstanceType.REPO)
    monkeypatch.setenv('OPPIE_HOME', str(home))
    result = Instance.detect()

    assert result == home.resolve()


def test_detect_oppie_home_env_var_invalid(tmp_path, monkeypatch):
    monkeypatch.setenv('OPPIE_HOME', str(tmp_path / 'bad'))

    with pytest.raises(FileNotFoundError, match='No valid instance'):
        Instance.detect()


def test_detect_cwd_walk(tmp_path, monkeypatch):
    home = tmp_path / '.oppie'
    Instance.create(home=home, instance_type=InstanceType.REPO)
    nested = tmp_path / 'sub' / 'dir'
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    monkeypatch.delenv('OPPIE_HOME', raising=False)
    result = Instance.detect()

    assert result == home.resolve()


def test_detect_cwd_walk_from_root(tmp_path, monkeypatch):
    home = tmp_path / '.oppie'
    Instance.create(home=home, instance_type=InstanceType.REPO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('OPPIE_HOME', raising=False)
    result = Instance.detect()

    assert result == home.resolve()


def test_detect_no_instance_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('OPPIE_HOME', raising=False)

    with pytest.raises(FileNotFoundError, match="Run 'oppie init'"):
        Instance.detect()


def test_detect_priority_home_over_env(tmp_path, monkeypatch):
    home_a = tmp_path / 'a' / '.oppie'
    home_b = tmp_path / 'b' / '.oppie'
    Instance.create(home=home_a, instance_type=InstanceType.REPO)
    Instance.create(home=home_b, instance_type=InstanceType.REPO)
    monkeypatch.setenv('OPPIE_HOME', str(home_b))
    result = Instance.detect(home=home_a)

    assert result == home_a.resolve()


def test_detect_priority_env_over_cwd(tmp_path, monkeypatch):
    cwd_home = tmp_path / 'cwd_project' / '.oppie'
    env_home = tmp_path / 'env_project' / '.oppie'
    Instance.create(home=cwd_home, instance_type=InstanceType.REPO)
    Instance.create(home=env_home, instance_type=InstanceType.REPO)
    monkeypatch.chdir(tmp_path / 'cwd_project')
    monkeypatch.setenv('OPPIE_HOME', str(env_home))
    result = Instance.detect()

    assert result == env_home.resolve()
