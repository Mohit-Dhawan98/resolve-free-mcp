# resolve-free-mcp

Let Claude edit video in the **free** edition of DaVinci Resolve.

Resolve's scripting API is only reachable from outside the app in the paid
Studio edition. The free edition still runs Lua, but only from its own console.
This project gets around that with a file mailbox: a small Lua loop running
inside Resolve picks up commands from a folder, and an MCP server on the outside
writes them.

```
Claude ── MCP ──> server.py ── inbox/cmd_N.lua ──> bridge.lua (inside Resolve's console)
                      ^                                   │
                      └──── outbox/res_N_k.xml <──────────┘
```

## The return channel

Getting commands in is easy. Getting results out is the interesting part: the
console's Lua has no usable way to write an arbitrary file, but it can export a
timeline. So each command:

1. runs its Lua body inside `pcall`,
2. cuts the result string into 110-character chunks,
3. renames a scratch timeline `__out__<k>~<chunk>` and exports it as FCP7 XML,
4. exports a final `__out__done` marker.

The server waits for the marker, then reads the chunks back out of the
`<name>` element of each XML file. Characters a timeline name cannot hold are
replaced with `_`, so results are best kept to simple `key=value;key=value`
strings.

## Tools

| Tool | What it does |
|---|---|
| `bridge_status` | Resolve version, current project and timeline |
| `list_timelines` | Timelines in the current project |
| `import_media` | Import files into the media pool, skipping ones already there |
| `build_timeline` | Create a timeline (default 1080×1920, 30 fps) and append source ranges in order |
| `set_clip_zoom` | Zoom a clip, for example to fill a vertical frame |
| `add_text_card` | Add a one- or two-line text card over a clip through a Fusion comp |
| `render` | Render a timeline and report job status |
| `run_lua` | Run any Lua body inside Resolve, with `r`, `pm`, `p`, `mp`, `bmd`, `fu` in scope |
| `stop_bridge` | Tell the bridge loop to exit |

`run_lua` is the escape hatch: anything the Resolve API can do from the console
can be done through it.

## Setup

Requires DaVinci Resolve (developed against 21.1, free edition, macOS) and
[uv](https://docs.astral.sh/uv/).

1. Install the bridge. This creates `~/resolve_bridge` and prints the line to
   paste into Resolve:

   ```bash
   python3 install_bridge.py
   ```

2. In Resolve, once per session: **Workspace > Console > Lua**, paste the
   printed `fu:RunScript("…/bridge.lua")` line. The console is busy while the
   bridge runs; `stop_bridge` ends it.

3. Add the server to Claude Desktop (**Settings > Developer > Edit Config**):

   ```json
   {
     "mcpServers": {
       "resolve": {
         "command": "/path/to/uv",
         "args": ["run", "--directory", "/path/to/resolve-free-mcp", "server.py"]
       }
     }
   }
   ```

   If the bridge lives somewhere other than `~/resolve_bridge`, set
   `RESOLVE_BRIDGE_DIR` in the server's `env`.

4. `add_text_card` defaults to Cormorant SC and Cormorant Garamond (both free on
   Google Fonts). A font that is not installed makes the render fail, so install
   them or pass your own `font1` / `font2`.

## Limits

- One command at a time; commands are numbered and processed in order.
- Results pass through timeline names, so they are short and lose punctuation.
- Paths are passed to Resolve as-is: use absolute paths.
- Built for one person's reel-editing workflow on macOS. Not tested on Windows
  or Linux, or on Resolve Studio (which does not need this workaround).

## License

MIT. Not affiliated with Blackmagic Design.
