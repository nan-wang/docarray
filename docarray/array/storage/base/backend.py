from abc import ABC
from dataclasses import is_dataclass, asdict
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ....typing import DocumentArraySourceType, ArrayType


class BaseBackendMixin(ABC):
    TYPE_MAP: Dict

    def _init_storage(
        self,
        _docs: Optional['DocumentArraySourceType'] = None,
        copy: bool = False,
        *args,
        **kwargs
    ):
        self._load_offset2ids()

    def _get_storage_infos(self) -> Optional[Dict]:
        if hasattr(self, '_config') and is_dataclass(self._config):
            return {k: str(v) for k, v in asdict(self._config).items()}

    def _map_id(self, _id: str) -> str:
        return _id

    def _map_column(self, value, col_type) -> str:
        return self.TYPE_MAP[col_type][1](value)

    def _map_embedding(self, embedding: 'ArrayType') -> 'ArrayType':
        from ....math.ndarray import to_numpy_array

        return to_numpy_array(embedding)

    def _map_type(self, col_type: str) -> str:
        return self.TYPE_MAP[col_type][0]
