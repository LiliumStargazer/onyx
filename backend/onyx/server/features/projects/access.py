from onyx.configs.chat_configs import PROJECTS_ENABLED
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError


def require_projects_enabled() -> None:
    if not PROJECTS_ENABLED:
        raise OnyxError(OnyxErrorCode.INSUFFICIENT_PERMISSIONS, "Projects are disabled")
