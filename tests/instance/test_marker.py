import pytest

from oppie.config import InstanceType
from oppie.instance import Marker


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
