from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from onyx.background.celery.tasks.pruning.tasks import try_creating_prune_generator_task
from onyx.configs.constants import DocumentSource
from onyx.db.models import ConnectorCredentialPair


def test_wikijs_snapshot_cannot_schedule_pruning() -> None:
    connector_pair = cast(
        ConnectorCredentialPair,
        SimpleNamespace(id=1, connector=SimpleNamespace(source=DocumentSource.WIKIJS)),
    )
    unused_dependency = Mock()

    assert (
        try_creating_prune_generator_task(
            unused_dependency,
            connector_pair,
            unused_dependency,
            unused_dependency,
            "tenant",
        )
        is None
    )
    unused_dependency.assert_not_called()
