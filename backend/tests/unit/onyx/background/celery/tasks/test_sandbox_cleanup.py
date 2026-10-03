from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from celery import Task

from onyx.background.celery.tasks.build import tasks
from onyx.feature_flags.interface import FeatureFlagProvider, NoOpFeatureFlagProvider


@pytest.mark.parametrize(
    ("craft_enabled", "feature_flags_configured", "should_run_cleanup"),
    [(False, False, False), (True, False, True), (False, True, True)],
)
def test_sandbox_cleanup_skips_only_disabled_env_fallback(
    craft_enabled: bool,
    feature_flags_configured: bool,
    should_run_cleanup: bool,
) -> None:
    provider = (
        MagicMock(spec=FeatureFlagProvider)
        if feature_flags_configured
        else NoOpFeatureFlagProvider()
    )
    with (
        patch.object(tasks, "ENABLE_CRAFT", craft_enabled),
        patch.object(tasks, "get_default_feature_flag_provider", return_value=provider),
        patch.object(tasks, "get_redis_client") as redis_client,
    ):
        redis_client.return_value.lock.return_value.acquire.return_value = False

        assert (
            cast(Task, tasks.cleanup_idle_sandboxes_task).run(tenant_id="test") is None
        )

        assert redis_client.called is should_run_cleanup
