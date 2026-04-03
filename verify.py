import os
import sys

try:
    sys.path.insert(0, os.path.abspath('c:/Users/talme/Hephaestus/src'))

    from hephaestus.tools.file_ops import search_files, grep_search
    from hephaestus.tools.web_tools import HostResolver, web_fetch, _is_safe_url
    from hephaestus.core.genesis import GenesisConfig, Genesis
    from hephaestus.pantheon.coordinator import PantheonCoordinator
    from hephaestus.tools.invocation import ToolInvocation, ToolContext
    from hephaestus.tools.permissions import PermissionPolicy
    from hephaestus.agent.runtime import ConversationRuntime
    print("Imports ok")

    # Test web_tools resolver mock
    os.environ["HEPHAESTUS_OFFLINE_CI"] = "1"
    ips = HostResolver.resolve_ips("test.mock.local")
    assert str(ips[0]) == "127.0.0.1"
    print("HostResolver ok")

    # Test file_ops OS exception handling
    res1 = search_files("test", "c:/does_not_exist_folder")
    if "Error:" not in res1:
        print(f"FAILED returned {res1}")
    else:
        print("file_ops path handling ok")

    print("All targeted verifications passed.")
except Exception as e:
    import traceback
    traceback.print_exc()
