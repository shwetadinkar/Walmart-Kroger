"""Durable staging, checkpoints and atomic latest-success pointer; per-store run locks."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path

class StorageError(RuntimeError):
    pass

def _key(k: str) -> str:
    if not k or k.startswith("/") or ".." in k or "\\" in k or not re.fullmatch(r"[a-zA-Z0-9_./-]+", k):
        raise StorageError(f"Unsafe storage key {k!r}")
    return k

class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
    def write(self, key: str, contents: bytes) -> None:
        path = self.root / _key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp." + str(os.getpid()))
        with tmp.open("wb") as f:
            f.write(contents)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    def read(self, key: str) -> bytes | None:
        path = self.root / _key(key)
        return path.read_bytes() if path.is_file() else None
    def delete(self, key: str) -> None:
        (self.root / _key(key)).unlink(missing_ok=True)
    @contextmanager
    def locked(self, store_id: str):
        """Non-blocking local store lock on POSIX and Windows."""
        path = self.root / "locks" / (store_id + ".lock")
        path.parent.mkdir(exist_ok=True)
        with path.open("a+b") as f:
            f.seek(0, 2)
            if f.tell() == 0:
                f.write(b"0")
                f.flush()
            f.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as ex:
                raise StorageError("Another run currently holds this store lock") from ex
            try:
                yield
            finally:
                if os.name == "nt":
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

class AzureBlobStorage:
    """Checkpoints are remote: Azure Container Apps ephemeral disks are NOT used."""
    def __init__(self, connection_string: str, container_name: str):
        try:
            from azure.storage.blob import BlobServiceClient
            from azure.core.exceptions import ResourceExistsError
        except ImportError as ex:
            raise StorageError("Install package with pip install '.[azure]'") from ex
        self.container = BlobServiceClient.from_connection_string(connection_string).get_container_client(container_name)
        try:
            self.container.create_container()
        except ResourceExistsError:
            pass
    def write(self, key: str, contents: bytes) -> None:
        self.container.get_blob_client(_key(key)).upload_blob(contents, overwrite=True)
    def read(self, key: str) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError
        try:
            return self.container.get_blob_client(_key(key)).download_blob().readall()
        except ResourceNotFoundError:
            return None
    def delete(self, key: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError
        try:
            self.container.delete_blob(_key(key))
        except ResourceNotFoundError:
            pass
    def assert_lock_held(self) -> None:
        lease = getattr(self, "_active_lease", None)
        if lease is None:
            raise StorageError("No active Azure run lock")
        try:
            lease.renew()
        except Exception as ex:
            raise StorageError("Azure run lock was lost") from ex

    @contextmanager
    def locked(self, store_id: str):
        from azure.core.exceptions import ResourceExistsError, HttpResponseError
        blob = self.container.get_blob_client(f"locks/{store_id}.lock")
        try:
            blob.upload_blob(b"lock", overwrite=False)
        except ResourceExistsError:
            pass
        try:
            lease = blob.acquire_lease(lease_duration=60)
        except HttpResponseError as ex:
            raise StorageError("Another run holds the Azure Blob lease for this store") from ex
        self._active_lease = lease
        shutdown = threading.Event()
        renewal_error: list[Exception] = []
        def renew():
            while not shutdown.wait(20):
                try:
                    lease.renew()
                except Exception as ex:
                    renewal_error.append(ex)
                    shutdown.set()
                    break
        thread = threading.Thread(target=renew, daemon=True)
        thread.start()
        try:
            yield
            if renewal_error:
                raise StorageError("Azure lock lease could not be renewed") from renewal_error[0]
        finally:
            shutdown.set()
            thread.join(timeout=25)
            self._active_lease = None
            try:
                lease.release()
            except Exception:
                pass

def read_json(storage, key: str):
    body = storage.read(key)
    return json.loads(body) if body is not None else None

def write_json(storage, key: str, value) -> None:
    storage.write(key, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))
