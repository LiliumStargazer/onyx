from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from onyx.background.celery.tasks.docprocessing.utils import should_index
from onyx.configs.constants import DocumentSource
from onyx.connectors.models import InputType
from onyx.db.connector import update_connector
from onyx.db.enums import (
    AccessType,
    ConnectorCredentialPairStatus,
    IndexingMode,
    IndexModelStatus,
)
from onyx.error_handling.exceptions import OnyxError
from onyx.server.documents.cc_pair import update_cc_pair_property
from onyx.server.documents.connector import (
    _validate_wikijs_configuration,
    update_connector_from_model,
)
from onyx.server.documents.models import (
    CCPropertyUpdateRequest,
    ConnectorBase,
    ConnectorUpdateRequest,
)


def test_wikijs_creation_does_not_enable_refresh_or_pruning() -> None:
    connector = ConnectorBase(
        name="wiki",
        source=DocumentSource.WIKIJS,
        input_type=InputType.LOAD_STATE,
        connector_specific_config={
            "visibility_folders": '{"Riservato":"interni"}',
            "role_visibility_map": '{"interni":["interni"],"tecnico":[],"agente":[],"concessionario":[]}',
        },
        refresh_freq=600,
    )
    with pytest.raises(OnyxError):
        _validate_wikijs_configuration(connector)
    connector.refresh_freq = None
    connector.prune_freq = 600
    with pytest.raises(OnyxError):
        _validate_wikijs_configuration(connector)
    connector.prune_freq = None
    _validate_wikijs_configuration(connector)


@pytest.mark.parametrize("last_successful_index_time", [None, "successful-run"])
def test_wikijs_refresh_requires_successful_first_run(
    last_successful_index_time: str | None,
) -> None:
    cc_pair = MagicMock()
    cc_pair.connector.source = DocumentSource.WIKIJS
    cc_pair.connector.refresh_freq = None
    cc_pair.last_successful_index_time = last_successful_index_time
    db_session = MagicMock()
    with (
        patch(
            "onyx.server.documents.cc_pair.get_connector_credential_pair_from_id_for_user",
            return_value=cc_pair,
        ),
        patch(
            "onyx.server.documents.cc_pair.get_cc_pair_ids_for_connector",
            return_value=[1],
        ),
        patch(
            "onyx.server.documents.cc_pair.verify_user_can_edit_all_cc_pairs",
            return_value=True,
        ),
    ):
        request = CCPropertyUpdateRequest(name="refresh_frequency", value="600")
        if last_successful_index_time is None:
            with pytest.raises(OnyxError):
                update_cc_pair_property(1, request, MagicMock(), db_session)
            db_session.commit.assert_not_called()
            assert cc_pair.connector.refresh_freq is None
        else:
            update_cc_pair_property(1, request, MagicMock(), db_session)
            assert cc_pair.connector.refresh_freq == 600
            db_session.commit.assert_called_once()


def test_wikijs_shared_refresh_waits_for_each_connection_first_success() -> None:
    connector = MagicMock(id=1, source=DocumentSource.WIKIJS, refresh_freq=600)
    first_connection = MagicMock(
        id=1,
        connector=connector,
        status=ConnectorCredentialPairStatus.ACTIVE,
        indexing_trigger=None,
        last_successful_index_time=datetime.now(timezone.utc),
    )
    second_connection = MagicMock(
        id=2,
        connector=connector,
        status=ConnectorCredentialPairStatus.ACTIVE,
        indexing_trigger=None,
        last_successful_index_time=None,
    )
    search_settings = MagicMock(id=1, status=IndexModelStatus.PRESENT)
    previous_attempt = MagicMock(
        time_updated=datetime.now(timezone.utc) - timedelta(minutes=20)
    )
    with (
        patch(
            "onyx.background.celery.tasks.docprocessing.utils.get_last_attempt_for_cc_pair",
            return_value=previous_attempt,
        ) as get_last_attempt,
        patch(
            "onyx.background.celery.tasks.docprocessing.utils.is_in_repeated_error_state",
            return_value=False,
        ),
        patch(
            "onyx.background.celery.tasks.docprocessing.utils.get_db_current_time",
            return_value=datetime.now(timezone.utc),
        ),
    ):
        assert should_index(first_connection, search_settings, False, MagicMock())
        assert not should_index(second_connection, search_settings, False, MagicMock())
        get_last_attempt.return_value = None
        assert should_index(second_connection, search_settings, False, MagicMock())
        get_last_attempt.return_value = previous_attempt
        second_connection.indexing_trigger = IndexingMode.REINDEX
        assert should_index(second_connection, search_settings, False, MagicMock())
        second_connection.indexing_trigger = None
        second_connection.last_successful_index_time = datetime.now(timezone.utc)
        assert should_index(second_connection, search_settings, False, MagicMock())


def test_wikijs_connector_update_cannot_enable_refresh_early() -> None:
    connector = MagicMock()
    connector.refresh_freq = None
    request = ConnectorUpdateRequest(
        name="wiki",
        source=DocumentSource.WIKIJS,
        input_type=InputType.LOAD_STATE,
        connector_specific_config={
            "visibility_folders": '{"Riservato":"interni"}',
            "role_visibility_map": '{"interni":["interni"],"tecnico":[],"agente":[],"concessionario":[]}',
        },
        access_type=AccessType.PRIVATE,
        refresh_freq=600,
    )
    with (
        patch(
            "onyx.server.documents.connector.fetch_connector_by_id",
            return_value=connector,
        ),
        patch("onyx.server.documents.connector.update_connector") as update,
        pytest.raises(OnyxError),
    ):
        update_connector_from_model(1, request, MagicMock(), MagicMock())
    update.assert_not_called()

    connector.source = DocumentSource.WEB
    connector.refresh_freq = 600
    with (
        patch(
            "onyx.server.documents.connector.fetch_connector_by_id",
            return_value=connector,
        ),
        patch("onyx.server.documents.connector.update_connector") as update,
        pytest.raises(OnyxError),
    ):
        update_connector_from_model(1, request, MagicMock(), MagicMock())
    update.assert_not_called()

    connector.source = DocumentSource.WIKIJS
    with (
        patch(
            "onyx.server.documents.connector.fetch_connector_by_id",
            return_value=connector,
        ),
        patch(
            "onyx.server.documents.connector.update_connector", return_value=None
        ) as update,
        pytest.raises(OnyxError),
    ):
        update_connector_from_model(1, request, MagicMock(), MagicMock())
    update.assert_called_once()


def test_wikijs_connector_update_keeps_native_pruning_disabled() -> None:
    connector = MagicMock()
    connector.name = "wiki"
    connector.source = DocumentSource.WIKIJS
    db_session = MagicMock()
    with patch("onyx.db.connector.fetch_connector_by_id", return_value=connector):
        update_connector(
            1,
            ConnectorBase(
                name="wiki",
                source=DocumentSource.WIKIJS,
                input_type=InputType.LOAD_STATE,
                connector_specific_config={},
            ),
            db_session,
        )
    assert connector.prune_freq is None


def test_wikijs_native_pruning_cannot_be_enabled() -> None:
    cc_pair = MagicMock()
    cc_pair.connector.source = DocumentSource.WIKIJS
    db_session = MagicMock()
    with (
        patch(
            "onyx.server.documents.cc_pair.get_connector_credential_pair_from_id_for_user",
            return_value=cc_pair,
        ),
        patch(
            "onyx.server.documents.cc_pair.get_cc_pair_ids_for_connector",
            return_value=[1],
        ),
        patch(
            "onyx.server.documents.cc_pair.verify_user_can_edit_all_cc_pairs",
            return_value=True,
        ),
        pytest.raises(OnyxError),
    ):
        update_cc_pair_property(
            1,
            CCPropertyUpdateRequest(name="pruning_frequency", value="600"),
            MagicMock(),
            db_session,
        )
    db_session.commit.assert_not_called()
