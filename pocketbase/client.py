from __future__ import annotations

from typing import Any, Dict

import httpx

from pocketbase.errors import ClientResponseError
from pocketbase.models import FileUpload
from pocketbase.models.record import Record
from pocketbase.services.admin_service import AdminService
from pocketbase.services.backups_service import BackupsService
from pocketbase.services.collection_service import CollectionService
from pocketbase.services.files_service import FileService
from pocketbase.services.health_service import HealthService
from pocketbase.services.log_service import LogService
from pocketbase.services.realtime_service import RealtimeService
from pocketbase.services.record_service import RecordService
from pocketbase.services.settings_service import SettingsService
from pocketbase.stores.base_auth_store import AuthStore, BaseAuthStore


class Client:
    def __init__(
        self,
        base_url: str = "/",
        lang: str = "en-US",
        auth_store: AuthStore | None = None,
        timeout: float = 120,
        http_client: httpx.Client | None = None,
        auto_snake_case: bool = True,
    ) -> None:
        self.base_url = base_url
        self.lang = lang
        self.auth_store = auth_store or BaseAuthStore()  # LocalAuthStore()
        self.timeout = timeout
        self.http_client = http_client or httpx.Client()
        self.auto_snake_case = auto_snake_case
        # services
        self.admins = AdminService(self)
        self.backups = BackupsService(self)
        self.collections = CollectionService(self)
        self.files = FileService(self)
        self.health = HealthService(self)
        self.logs = LogService(self)
        self.settings = SettingsService(self)
        self.realtime = RealtimeService(self)
        self.record_service: Dict[str, RecordService] = {}

    def _send(self, path: str, req_config: dict[str, Any]) -> httpx.Response:
        """Sends an api http request returning response object."""
        config: dict[str, Any] = {"method": "GET"}
        config.update(req_config)
        # check if Authorization header can be added
        if self.auth_store.token and (
            "headers" not in config or "Authorization" not in config["headers"]
        ):
            config["headers"] = config.get("headers", {})
            config["headers"].update({"Authorization": self.auth_store.token})
        # build url + path
        url = self.build_url(path)
        # send the request
        method = config.get("method", "GET")
        params = config.get("params", None)
        headers = config.get("headers", None)
        body: dict[str, Any] | None = config.get("body", None)
        # handle requests including files as multipart:
        data: dict[str, Any] | None = {}
        files = ()
        for k, v in (body if isinstance(body, dict) else {}).items():
            if isinstance(v, FileUpload):
                files += v.get(k)
            else:
                data[k] = v
        if len(files) > 0:
            # discard body, switch to multipart encoding
            body = None
        else:
            # discard files+data (do not use multipart encoding)
            files = None
            data = None
        try:
            response = self.http_client.request(
                method=method,
                url=url,
                params=params,
                headers=headers,
                json=body,
                data=data,
                files=files,  # type: ignore
                timeout=self.timeout,
            )
        except Exception as e:
            raise ClientResponseError(
                f"General request error. Original error: {e}",
                original_error=e,
            )
        return response

    def collection(self, id_or_name: str) -> RecordService:
        """Returns the RecordService associated to the specified collection."""
        if id_or_name not in self.record_service:
            self.record_service[id_or_name] = RecordService(self, id_or_name)
        return self.record_service[id_or_name]

    def send_raw(self, path: str, req_config: dict[str, Any]) -> bytes:
        """Sends an api http request returning raw bytes response."""
        response = self._send(path, req_config)
        return response.content

    def send(self, path: str, req_config: dict[str, Any]) -> Any:
        """Sends an api http request."""
        response = self._send(path, req_config)
        try:
            data = response.json()
        except Exception:
            data = None
        if response.status_code >= 400:
            raise ClientResponseError(
                f"Response error. Status code:{response.status_code}",
                url=str(response.url),
                status=response.status_code,
                data=data,
            )
        return data

    def build_url(self, path: str) -> str:
        url = self.base_url
        if not self.base_url.endswith("/"):
            url += "/"
        if path.startswith("/"):
            path = path[1:]
        return url + path

    # TODO: add deprecated decorator
    def get_file_url(
        self,
        record: Record,
        filename: str,
        query_params: dict[str, Any] | None = None,
    ):
        return self.files.get_url(record, filename, query_params)

    # TODO: add deprecated decorator
    def get_file_token(self) -> str:
        return self.files.get_token()
