import yaml


def write_yaml(path, data):
    """Helper to write YAML data to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        yaml.dump(data, f)
