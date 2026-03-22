def create_artifact_dirs(home):
    for d in ['ask', 'plans', 'applies', 'reports', 'context']:
        (home / 'artifacts' / d).mkdir(parents=True, exist_ok=True)
