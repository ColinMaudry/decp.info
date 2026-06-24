class FakeStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload_bytes(self, key, data):
        self.objects[key] = data

    def download_bytes(self, key):
        return self.objects[key]

    def list_keys(self, prefix):
        return [k for k in self.objects if k.startswith(prefix)]

    def delete(self, key):
        self.objects.pop(key, None)
