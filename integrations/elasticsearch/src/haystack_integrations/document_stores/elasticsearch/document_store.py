# SPDX-FileCopyrightText: 2023-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping
from typing import Any, Dict, List, Literal, Optional, Union

import numpy as np
from elastic_transport import NodeConfig
from haystack import default_from_dict, default_to_dict, logging
from haystack.dataclasses import Document
from haystack.document_stores.errors import DocumentStoreError, DuplicateDocumentError
from haystack.document_stores.types import DuplicatePolicy
from haystack.version import __version__ as haystack_version

from elasticsearch import AsyncElasticsearch, Elasticsearch, helpers

from .filters import _normalize_filters

logger = logging.getLogger(__name__)

Hosts = Union[str, List[Union[str, Mapping[str, Union[str, int]], NodeConfig]]]

# document scores are essentially unbounded and will be scaled to values between 0 and 1 if scale_score is set to
# True. Scaling uses the expit function (inverse of the logit function) after applying a scaling factor
# (e.g., BM25_SCALING_FACTOR for the bm25_retrieval method).
# Larger scaling factor decreases scaled scores. For example, an input of 10 is scaled to 0.99 with
# BM25_SCALING_FACTOR=2 but to 0.78 with BM25_SCALING_FACTOR=8 (default). The defaults were chosen empirically.
# Increase the default if most unscaled scores are larger than expected (>30) and otherwise would incorrectly
# all be mapped to scores ~1.
BM25_SCALING_FACTOR = 8
DOC_ALREADY_EXISTS = 409


class ElasticsearchDocumentStore:
    """
    An ElasticsearchDocumentStore instance that works with Elastic Cloud or your own
    Elasticsearch cluster.

    Usage example (Elastic Cloud):
    ```python
    from haystack.document_store.elasticsearch import ElasticsearchDocumentStore
    document_store = ElasticsearchDocumentStore(cloud_id="YOUR_CLOUD_ID", api_key="YOUR_API_KEY")
    ```

    Usage example (self-hosted Elasticsearch instance):
    ```python
    from haystack.document_store.elasticsearch import ElasticsearchDocumentStore
    document_store = ElasticsearchDocumentStore(hosts="http://localhost:9200")
    ```
    In the above example we connect with security disabled just to show the basic usage.
    We strongly recommend to enable security so that only authorized users can access your data.

    For more details on how to connect to Elasticsearch and configure security,
    see the official Elasticsearch
    [documentation](https://www.elastic.co/guide/en/elasticsearch/client/python-api/current/connecting.html)

    All extra keyword arguments will be passed to the Elasticsearch client.
    """

    def __init__(
        self,
        *,
        hosts: Optional[Hosts] = None,
        custom_mapping: Optional[Dict[str, Any]] = None,
        index: str = "default",
        embedding_similarity_function: Literal["cosine", "dot_product", "l2_norm", "max_inner_product"] = "cosine",
        **kwargs: Any,
    ):
        """
        Creates a new ElasticsearchDocumentStore instance.

        It will also try to create that index if it doesn't exist yet. Otherwise, it will use the existing one.

        One can also set the similarity function used to compare Documents embeddings. This is mostly useful
        when using the `ElasticsearchDocumentStore` in a Pipeline with an `ElasticsearchEmbeddingRetriever`.

        For more information on connection parameters, see the official Elasticsearch
        [documentation](https://www.elastic.co/guide/en/elasticsearch/client/python-api/current/connecting.html)

        For the full list of supported kwargs, see the official Elasticsearch
        [reference](https://elasticsearch-py.readthedocs.io/en/stable/api.html#module-elasticsearch)

        :param hosts: List of hosts running the Elasticsearch client.
        :param custom_mapping: Custom mapping for the index. If not provided, a default mapping will be used.
        :param index: Name of index in Elasticsearch.
        :param embedding_similarity_function: The similarity function used to compare Documents embeddings.
            This parameter only takes effect if the index does not yet exist and is created.
            To choose the most appropriate function, look for information about your embedding model.
            To understand how document scores are computed, see the Elasticsearch
            [documentation](https://www.elastic.co/guide/en/elasticsearch/reference/current/dense-vector.html#dense-vector-params)
        :param **kwargs: Optional arguments that `Elasticsearch` takes.
        """
        self._hosts = hosts
        self._client: Optional[Elasticsearch] = None
        self._async_client: Optional[AsyncElasticsearch] = None
        self._index = index
        self._embedding_similarity_function = embedding_similarity_function
        self._custom_mapping = custom_mapping
        self._kwargs = kwargs
        self._initialized = False

        if self._custom_mapping and not isinstance(self._custom_mapping, Dict):
            msg = "custom_mapping must be a dictionary"
            raise ValueError(msg)

    def _ensure_initialized(self):
        """
        Ensures both sync and async clients are initialized and the index exists.
        """
        if not self._initialized:
            headers = self._kwargs.pop("headers", {})
            headers["user-agent"] = f"haystack-py-ds/{haystack_version}"

            # Initialize both sync and async clients
            self._client = Elasticsearch(
                self._hosts,
                headers=headers,
                **self._kwargs,
            )
            self._async_client = AsyncElasticsearch(
                self._hosts,
                headers=headers,
                **self._kwargs,
            )

            # Check client connection, this will raise if not connected
            self._client.info()

            if self._custom_mapping:
                mappings = self._custom_mapping
            else:
                # Configure mapping for the embedding field if none is provided
                mappings = {
                    "properties": {
                        "embedding": {
                            "type": "dense_vector",
                            "index": True,
                            "similarity": self._embedding_similarity_function,
                        },
                        "content": {"type": "text"},
                    },
                    "dynamic_templates": [
                        {
                            "strings": {
                                "path_match": "*",
                                "match_mapping_type": "string",
                                "mapping": {
                                    "type": "keyword",
                                },
                            }
                        }
                    ],
                }

            # Create the index if it doesn't exist
            if not self._client.indices.exists(index=self._index):
                self._client.indices.create(index=self._index, mappings=mappings)

            self._initialized = True

    @property
    def client(self) -> Elasticsearch:
        """
        Returns the synchronous Elasticsearch client, initializing it if necessary.
        """
        self._ensure_initialized()
        assert self._client is not None  # noqa: S101
        return self._client

    @property
    def async_client(self) -> AsyncElasticsearch:
        """
        Returns the asynchronous Elasticsearch client, initializing it if necessary.
        """
        self._ensure_initialized()
        assert self._async_client is not None  # noqa: S101
        return self._async_client

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes the component to a dictionary.

        :returns:
            Dictionary with serialized data.
        """
        # This is not the best solution to serialise this class but is the fastest to implement.
        # Not all kwargs types can be serialised to text so this can fail. We must serialise each
        # type explicitly to handle this properly.
        return default_to_dict(
            self,
            hosts=self._hosts,
            custom_mapping=self._custom_mapping,
            index=self._index,
            embedding_similarity_function=self._embedding_similarity_function,
            **self._kwargs,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ElasticsearchDocumentStore":
        """
        Deserializes the component from a dictionary.

        :param data:
            Dictionary to deserialize from.
        :returns:
            Deserialized component.
        """
        return default_from_dict(cls, data)

    def count_documents(self) -> int:
        """
        Returns how many documents are present in the document store.

        :returns:
            Number of documents in the document store.
        """
        self._ensure_initialized()
        return self.client.count(index=self._index)["count"]

    async def count_documents_async(self) -> int:
        """
        Asynchronously returns how many documents are present in the document store.
        :returns: Number of documents in the document store.
        """
        self._ensure_initialized()
        result = await self._async_client.count(index=self._index)  # type: ignore
        return result["count"]

    def _search_documents(self, **kwargs: Any) -> List[Document]:
        """
        Calls the Elasticsearch client's search method and handles pagination.
        """
        top_k = kwargs.get("size")
        if top_k is None and "knn" in kwargs and "k" in kwargs["knn"]:
            top_k = kwargs["knn"]["k"]

        documents: List[Document] = []
        from_ = 0
        # Handle pagination
        while True:
            res = self.client.search(
                index=self._index,
                from_=from_,
                **kwargs,
            )

            documents.extend(self._deserialize_document(hit) for hit in res["hits"]["hits"])  # type: ignore
            from_ = len(documents)

            if top_k is not None and from_ >= top_k:
                break
            if from_ >= res["hits"]["total"]["value"]:
                break
        return documents

    async def _search_documents_async(self, **kwargs: Any) -> List[Document]:
        """
        Asynchronously calls the Elasticsearch client's search method and handles pagination.
        """
        top_k = kwargs.get("size")
        if top_k is None and "knn" in kwargs and "k" in kwargs["knn"]:
            top_k = kwargs["knn"]["k"]

        documents: List[Document] = []
        from_ = 0

        # handle pagination
        while True:
            res = await self._async_client.search(index=self._index, from_=from_, **kwargs)  # type: ignore
            documents.extend(self._deserialize_document(hit) for hit in res["hits"]["hits"])  # type: ignore
            from_ = len(documents)

            if top_k is not None and from_ >= top_k:
                break

            if from_ >= res["hits"]["total"]["value"]:
                break

        return documents

    def filter_documents(self, filters: Optional[Dict[str, Any]] = None) -> List[Document]:
        """
        The main query method for the document store. It retrieves all documents that match the filters.

        :param filters: A dictionary of filters to apply. For more information on the structure of the filters,
            see the official Elasticsearch
            [documentation](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html)
        :returns: List of `Document`s that match the filters.
        """
        if filters and "operator" not in filters and "conditions" not in filters:
            msg = "Invalid filter syntax. See https://docs.haystack.deepset.ai/docs/metadata-filtering for details."
            raise ValueError(msg)

        self._ensure_initialized()
        query = {"bool": {"filter": _normalize_filters(filters)}} if filters else None
        documents = self._search_documents(query=query)
        return documents

    async def filter_documents_async(self, filters: Optional[Dict[str, Any]] = None) -> List[Document]:
        """
        Asynchronously retrieves all documents that match the filters.

        :param filters: A dictionary of filters to apply. For more information on the structure of the filters,
            see the official Elasticsearch
            [documentation](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html)
        :returns: List of `Document`s that match the filters.
        """
        if filters and "operator" not in filters and "conditions" not in filters:
            msg = "Invalid filter syntax. See https://docs.haystack.deepset.ai/docs/metadata-filtering for details."
            raise ValueError(msg)

        self._ensure_initialized()
        query = {"bool": {"filter": _normalize_filters(filters)}} if filters else None
        documents = await self._search_documents_async(query=query)
        return documents

    @staticmethod
    def _deserialize_document(hit: Dict[str, Any]) -> Document:
        """
        Creates a `Document` from the search hit provided.
        This is mostly useful in self.filter_documents().
        :param hit: A search hit from Elasticsearch.
        :returns: `Document` created from the search hit.
        """
        data = hit["_source"]

        if "highlight" in hit:
            data["metadata"]["highlighted"] = hit["highlight"]
        data["score"] = hit["_score"]

        return Document.from_dict(data)

    def write_documents(self, documents: List[Document], policy: DuplicatePolicy = DuplicatePolicy.NONE) -> int:
        """
        Writes `Document`s to Elasticsearch.

        :param documents: List of Documents to write to the document store.
        :param policy: DuplicatePolicy to apply when a document with the same ID already exists in the document store.
        :raises ValueError: If `documents` is not a list of `Document`s.
        :raises DuplicateDocumentError: If a document with the same ID already exists in the document store and
            `policy` is set to `DuplicatePolicy.FAIL` or `DuplicatePolicy.NONE`.
        :raises DocumentStoreError: If an error occurs while writing the documents to the document store.
        :returns: Number of documents written to the document store.
        """
        if len(documents) > 0:
            if not isinstance(documents[0], Document):
                msg = "param 'documents' must contain a list of objects of type Document"
                raise ValueError(msg)

        if policy == DuplicatePolicy.NONE:
            policy = DuplicatePolicy.FAIL

        action = "index" if policy == DuplicatePolicy.OVERWRITE else "create"

        elasticsearch_actions = []
        for doc in documents:
            doc_dict = doc.to_dict()

            if "sparse_embedding" in doc_dict:
                sparse_embedding = doc_dict.pop("sparse_embedding", None)
                if sparse_embedding:
                    logger.warning(
                        "Document {doc_id} has the `sparse_embedding` field set,"
                        "but storing sparse embeddings in Elasticsearch is not currently supported."
                        "The `sparse_embedding` field will be ignored.",
                        doc_id=doc.id,
                    )
            elasticsearch_actions.append(
                {
                    "_op_type": action,
                    "_id": doc.id,
                    "_source": doc_dict,
                }
            )

        documents_written, errors = helpers.bulk(
            client=self.client,
            actions=elasticsearch_actions,
            refresh="wait_for",
            index=self._index,
            raise_on_error=False,
            stats_only=False,
        )

        if errors:
            # with stats_only=False, errors is guaranteed to be a list of dicts
            assert isinstance(errors, list)  # noqa: S101
            duplicate_errors_ids = []
            other_errors = []
            for e in errors:
                error_type = e["create"]["error"]["type"]
                if policy == DuplicatePolicy.FAIL and error_type == "version_conflict_engine_exception":
                    duplicate_errors_ids.append(e["create"]["_id"])
                elif policy == DuplicatePolicy.SKIP and error_type == "version_conflict_engine_exception":
                    # when the policy is skip, duplication errors are OK and we should not raise an exception
                    continue
                else:
                    other_errors.append(e)

            if len(duplicate_errors_ids) > 0:
                msg = f"IDs '{', '.join(duplicate_errors_ids)}' already exist in the document store."
                raise DuplicateDocumentError(msg)

            if len(other_errors) > 0:
                msg = f"Failed to write documents to Elasticsearch. Errors:\n{other_errors}"
                raise DocumentStoreError(msg)

        return documents_written

    async def write_documents_async(
        self, documents: List[Document], policy: DuplicatePolicy = DuplicatePolicy.NONE
    ) -> int:
        """
        Asynchronously writes `Document`s to Elasticsearch.

        :param documents: List of Documents to write to the document store.
        :param policy: DuplicatePolicy to apply when a document with the same ID already exists in the document store.
        :raises ValueError: If `documents` is not a list of `Document`s.
        :raises DuplicateDocumentError: If a document with the same ID already exists in the document store and
            `policy` is set to `DuplicatePolicy.FAIL` or `DuplicatePolicy.NONE`.
        :raises DocumentStoreError: If an error occurs while writing the documents to the document store.
        :returns: Number of documents written to the document store.
        """
        self._ensure_initialized()

        if len(documents) > 0:
            if not isinstance(documents[0], Document):
                msg = "param 'documents' must contain a list of objects of type Document"
                raise ValueError(msg)

        if policy == DuplicatePolicy.NONE:
            policy = DuplicatePolicy.FAIL

        actions = []
        for doc in documents:
            doc_dict = doc.to_dict()

            if "sparse_embedding" in doc_dict:
                sparse_embedding = doc_dict.pop("sparse_embedding", None)
                if sparse_embedding:
                    logger.warning(
                        "Document {doc_id} has the `sparse_embedding` field set,"
                        "but storing sparse embeddings in Elasticsearch is not currently supported."
                        "The `sparse_embedding` field will be ignored.",
                        doc_id=doc.id,
                    )

            action = {
                "_op_type": "create" if policy == DuplicatePolicy.FAIL else "index",
                "_id": doc.id,
                "_source": doc_dict,
            }
            actions.append(action)

        try:
            success, failed = await helpers.async_bulk(
                client=self.async_client,
                actions=actions,
                index=self._index,
                refresh=True,
                raise_on_error=False,
                stats_only=False,
            )
            if failed:
                # with stats_only=False, failed is guaranteed to be a list of dicts
                assert isinstance(failed, list)  # noqa: S101
                if policy == DuplicatePolicy.FAIL:
                    for error in failed:
                        if "create" in error and error["create"]["status"] == DOC_ALREADY_EXISTS:
                            msg = f"ID '{error['create']['_id']}' already exists in the document store"
                            raise DuplicateDocumentError(msg)
                msg = f"Failed to write documents to Elasticsearch. Errors:\n{failed}"
                raise DocumentStoreError(msg)
            return success
        except Exception as e:
            msg = f"Failed to write documents to Elasticsearch: {e!s}"
            raise DocumentStoreError(msg) from e

    def delete_documents(self, document_ids: List[str]) -> None:
        """
        Deletes all documents with a matching document_ids from the document store.

        :param document_ids: the document ids to delete
        """
        helpers.bulk(
            client=self.client,
            actions=({"_op_type": "delete", "_id": id_} for id_ in document_ids),
            refresh="wait_for",
            index=self._index,
            raise_on_error=False,
        )

    async def delete_documents_async(self, document_ids: List[str]) -> None:
        """
        Asynchronously deletes all documents with a matching document_ids from the document store.

        :param document_ids: the document ids to delete
        """
        self._ensure_initialized()

        try:
            await helpers.async_bulk(
                client=self.async_client,
                actions=({"_op_type": "delete", "_id": id_} for id_ in document_ids),
                index=self._index,
                refresh=True,
            )
        except Exception as e:
            msg = f"Failed to delete documents from Elasticsearch: {e!s}"
            raise DocumentStoreError(msg) from e

    def _bm25_retrieval(
        self,
        query: str,
        *,
        filters: Optional[Dict[str, Any]] = None,
        fuzziness: str = "AUTO",
        top_k: int = 10,
        scale_score: bool = False,
    ) -> List[Document]:
        """
        Retrieves documents using BM25 retrieval.

        :param query: The query string to search for
        :param filters: Optional filters to narrow down the search space
        :param fuzziness: Fuzziness parameter for the search query
        :param top_k: Maximum number of documents to return
        :param scale_score: Whether to scale the similarity score to the range [0,1]
        :returns: List of Documents that match the query
        """
        if not query:
            msg = "query must be a non empty string"
            raise ValueError(msg)

        body: Dict[str, Any] = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fuzziness": fuzziness,
                                "type": "most_fields",
                                "operator": "OR",
                            }
                        }
                    ]
                }
            },
        }

        if filters:
            body["query"]["bool"]["filter"] = _normalize_filters(filters)

        documents = self._search_documents(**body)

        if scale_score:
            for doc in documents:
                if doc.score is None:
                    continue
                doc.score = float(1 / (1 + np.exp(-np.asarray(doc.score / BM25_SCALING_FACTOR))))

        return documents

    async def _bm25_retrieval_async(
        self,
        query: str,
        *,
        filters: Optional[Dict[str, Any]] = None,
        fuzziness: str = "AUTO",
        top_k: int = 10,
        scale_score: bool = False,
    ) -> List[Document]:
        """
        Asynchronously retrieves documents using BM25 retrieval.

        :param query: The query string to search for
        :param filters: Optional filters to narrow down the search space
        :param fuzziness: Fuzziness parameter for the search query
        :param top_k: Maximum number of documents to return
        :param scale_score: Whether to scale the similarity score to the range [0,1]
        :returns: List of Documents that match the query
        """
        self._ensure_initialized()

        if not query:
            msg = "query must be a non empty string"
            raise ValueError(msg)

        # Prepare the search body
        search_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "type": "most_fields",
                                "operator": "OR",
                                "fuzziness": fuzziness,
                            }
                        }
                    ]
                }
            },
        }

        if filters:
            search_body["query"]["bool"]["filter"] = _normalize_filters(filters)  # type:ignore

        documents = await self._search_documents_async(**search_body)

        if scale_score:
            for doc in documents:
                if doc.score is not None:
                    doc.score = float(1 / (1 + np.exp(-(doc.score / float(BM25_SCALING_FACTOR)))))

        return documents

    def _embedding_retrieval(
        self,
        query_embedding: List[float],
        *,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
        num_candidates: Optional[int] = None,
    ) -> List[Document]:
        """
        Retrieves documents using dense vector similarity search.

        :param query_embedding: Embedding vector to search for
        :param filters: Optional filters to narrow down the search space
        :param top_k: Maximum number of documents to return
        :param num_candidates: Number of candidates to consider in the search
        :returns: List of Documents most similar to query_embedding
        """
        if not query_embedding:
            msg = "query_embedding must be a non-empty list of floats"
            raise ValueError(msg)

        if not num_candidates:
            num_candidates = top_k * 10

        body: Dict[str, Any] = {
            "knn": {
                "field": "embedding",
                "query_vector": query_embedding,
                "k": top_k,
                "num_candidates": num_candidates,
            },
        }

        if filters:
            body["knn"]["filter"] = _normalize_filters(filters)

        docs = self._search_documents(**body)
        return docs

    async def _embedding_retrieval_async(
        self,
        query_embedding: List[float],
        *,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
        num_candidates: Optional[int] = None,
    ) -> List[Document]:
        """
        Asynchronously retrieves documents using dense vector similarity search.

        :param query_embedding: Embedding vector to search for
        :param filters: Optional filters to narrow down the search space
        :param top_k: Maximum number of documents to return
        :param num_candidates: Number of candidates to consider in the search
        :returns: List of Documents most similar to query_embedding
        """
        self._ensure_initialized()

        if not query_embedding:
            msg = "query_embedding must be a non-empty list of floats"
            raise ValueError(msg)

        # If num_candidates is not set, use top_k * 10 as default
        if num_candidates is None:
            num_candidates = top_k * 10

        # Prepare the search body
        search_body = {
            "knn": {
                "field": "embedding",
                "query_vector": query_embedding,
                "k": top_k,
                "num_candidates": num_candidates,
            },
        }

        if filters:
            search_body["knn"]["filter"] = _normalize_filters(filters)

        return await self._search_documents_async(**search_body)
