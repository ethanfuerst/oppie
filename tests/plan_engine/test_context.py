from oppie.plan.engine import _load_context
from oppie.providers.local import LocalProvider
from tests.helpers import setup_instance


def test_load_context_reads_existing_files(home, provider):
    (home / 'context' / 'vision.md').write_text('Our vision statement.')
    (home / 'context' / 'roadmap.md').write_text('Q1 goals.')

    result = _load_context(home)

    assert result == {'vision': 'Our vision statement.', 'roadmap': 'Q1 goals.'}


def test_load_context_skips_missing_files(home, provider):
    (home / 'context' / 'vision.md').write_text('Vision only.')

    result = _load_context(home)

    assert result == {'vision': 'Vision only.'}


def test_load_context_skips_empty_files(home, provider):
    (home / 'context' / 'vision.md').write_text('')
    (home / 'context' / 'roadmap.md').write_text('  ')

    result = _load_context(home)

    assert result == {}


def test_load_context_no_context_dir(tmp_path):
    home = setup_instance(tmp_path)
    # Remove the context dir that setup_instance creates
    (home / 'context').rmdir()
    provider = LocalProvider(home)

    result = _load_context(home)

    assert result == {}
    provider.close()
