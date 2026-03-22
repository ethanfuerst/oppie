import pytest

from oppie.config import InstanceType
from oppie.instance import Instance


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
