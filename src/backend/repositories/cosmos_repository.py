"""Lightweight Cosmos DB repository utilities."""

from __future__ import annotations

from typing import Any, Dict, Generic, Iterable, List, Optional, Type, TypeVar

from azure.cosmos.aio import ContainerProxy
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app_config import config

TModel = TypeVar("TModel")


def _serialize_model(model: Any) -> Dict[str, Any]:
    data = model.model_dump(mode="json", exclude_none=True)
    ttl = data.pop("ttl_seconds", None)
    if ttl is not None:
        data["ttl"] = ttl
    data["timestamp"] = data.get("timestamp")
    return data


def _deserialize_model(model_cls: Type[TModel], payload: Dict[str, Any]) -> TModel:
    ttl = payload.pop("ttl", None)
    if ttl is not None:
        payload["ttl_seconds"] = ttl
    return model_cls.model_validate(payload)


class CosmosRepository(Generic[TModel]):
    """Repository providing basic CRUD operations on a Cosmos container."""

    def __init__(self, container_name: str, model_cls: Type[TModel], partition_key_path: str):
        database = config.get_cosmos_database_client()
        self._container: ContainerProxy = database.get_container_client(container_name)
        self._model_cls = model_cls
        self._partition_key_field = partition_key_path.lstrip("/")

    async def upsert(self, model: TModel) -> TModel:
        payload = _serialize_model(model)
        response = await self._container.upsert_item(payload)
        return _deserialize_model(self._model_cls, response)

    async def read(self, item_id: str, partition_key: Any) -> Optional[TModel]:
        try:
            response = await self._container.read_item(item=item_id, partition_key=partition_key)
        except CosmosResourceNotFoundError:
            return None
        return _deserialize_model(self._model_cls, response)

    async def delete(self, item_id: str, partition_key: Any) -> None:
        try:
            await self._container.delete_item(item=item_id, partition_key=partition_key)
        except CosmosResourceNotFoundError:
            return

    async def query(self, query: str, parameters: Optional[Iterable[Dict[str, Any]]] = None) -> List[TModel]:
        items = self._container.query_items(
            query=query,
            parameters=list(parameters or []),
        )
        results: List[TModel] = []
        async for item in items:
            results.append(_deserialize_model(self._model_cls, item))
        return results

    async def list_partition(self, partition_key: Any, *, limit: int = 100) -> List[TModel]:
        query = f"SELECT * FROM c WHERE c.{self._partition_key_field}=@pk"
        params = [{"name": "@pk", "value": partition_key}]
        results = await self.query(query, params)
        return results[:limit]

    async def list_all(self, *, limit: Optional[int] = None) -> List[TModel]:
        query_iter = self._container.query_items(
            query="SELECT * FROM c",
        )
        results: List[TModel] = []
        async for item in query_iter:
            results.append(_deserialize_model(self._model_cls, item))
            if limit is not None and len(results) >= limit:
                break
        return results
