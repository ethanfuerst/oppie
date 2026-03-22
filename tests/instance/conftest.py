from pathlib import Path


def write_minimal_config(home: Path) -> None:
    """Write a minimal valid oppie.yaml into an instance's config dir."""
    import yaml

    config_path = home / 'config' / 'oppie.yaml'
    with open(config_path, 'w') as f:
        yaml.dump({'instance_type': 'repo', 'provider': {'type': 'local'}}, f)
