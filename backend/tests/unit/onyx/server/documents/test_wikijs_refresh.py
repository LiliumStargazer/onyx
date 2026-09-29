from unittest.mock import MagicMock, patch

import pytest

from onyx.configs.constants import DocumentSource
from onyx.connectors.models import InputType
from onyx.db.connector import update_connector
from onyx.db.enums import AccessType
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
        connector_specific_config={},
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


def test_wikijs_connector_update_cannot_enable_refresh_early() -> None:
    connector = MagicMock()
    connector.refresh_freq = None
    request = ConnectorUpdateRequest(
        name="wiki",
        source=DocumentSource.WIKIJS,
        input_type=InputType.LOAD_STATE,
        connector_specific_config={},
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

    connector.refresh_freq = 600
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
