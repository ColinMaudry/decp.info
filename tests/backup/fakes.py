class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload_bytes(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    def download_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def list_keys(self, prefix: str) -> list[str]:
        return [k for k in self.objects if k.startswith(prefix)]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
