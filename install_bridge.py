#!/usr/bin/env python3
"""Create the bridge directory and write bridge.lua with its absolute path baked in.

Resolve's Lua console cannot read environment variables, so the path the bridge
polls has to be a literal inside the script. Run this once:

    python3 install_bridge.py                # uses ~/resolve_bridge
    python3 install_bridge.py /some/other/dir
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    target = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/resolve_bridge"))
    for sub in ("inbox", "outbox"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    with open(os.path.join(HERE, "bridge.lua.template")) as f:
        lua = f.read().replace("@@BRIDGE_DIR@@", target)
    out = os.path.join(target, "bridge.lua")
    with open(out, "w") as f:
        f.write(lua)
    print(f"Bridge installed at {target}")
    print("In Resolve: Workspace > Console > Lua, then paste:")
    print(f'  fu:RunScript("{out}")')
    if target != os.path.expanduser("~/resolve_bridge"):
        print(f"Set RESOLVE_BRIDGE_DIR={target} in the MCP server's environment.")


if __name__ == "__main__":
    main()
