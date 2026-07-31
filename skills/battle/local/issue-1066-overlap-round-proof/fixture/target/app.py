def import_zip(name: str) -> str:
    if '..' in name:
        return 'blocked'
    return 'ok'
