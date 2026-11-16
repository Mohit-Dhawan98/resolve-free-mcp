"""Resolve (free) MCP server.

Talks to Resolve through bridge.lua running inside Resolve's Lua console:
  fu:RunScript("<bridge dir>/bridge.lua")     (install_bridge.py prints the exact line)
Commands go to <BRIDGE>/inbox/cmd_N.lua, results come back as exported timeline
names in <BRIDGE>/outbox/res_N_k.xml (chunked) + res_N.xml (done marker).
"""
import json, os, re, time
from mcp.server.fastmcp import FastMCP

BRIDGE = os.environ.get("RESOLVE_BRIDGE_DIR", os.path.expanduser("~/resolve_bridge"))
LUA_ROOT = os.environ.get("RESOLVE_BRIDGE_LUA_DIR", BRIDGE)
mcp = FastMCP("resolve")

PRELUDE = r'''
local N=@@N@@
local ROOT="@@ROOT@@/"
local r=resolve local pm=r:GetProjectManager() local p=pm:GetCurrentProject() local mp=p and p:GetMediaPool()
local function out(s)
  p=pm:GetCurrentProject() mp=p:GetMediaPool()
  local chunks={} local i=1 while i<=#s do chunks[#chunks+1]=s:sub(i,i+109) i=i+110 end
  if #chunks==0 then chunks={""} end
  local tl=nil
  for j=1,p:GetTimelineCount() do local t=p:GetTimelineByIndex(j) if t:GetName():sub(1,7)=="__out__" then tl=t end end
  if not tl then tl=mp:CreateEmptyTimeline("__out__") end
  for k,c in ipairs(chunks) do
    c=c:gsub("[^%w%s=;,%.%-_%+%(%)%[%]]","_")
    if not tl:SetName("__out__"..k.."~"..c) then tl:SetName("__out__"..k.."~UNNAMEABLE") end
    tl:Export(ROOT.."outbox/res_"..N.."_"..k..".xml", r.EXPORT_FCP_7_XML, r.EXPORT_NONE)
  end
  tl:SetName("__out__done")
  tl:Export(ROOT.."outbox/res_"..N..".xml", r.EXPORT_FCP_7_XML, r.EXPORT_NONE)
end
local ok,res=pcall(function()
@@BODY@@
end)
out((ok and "OK " or "ERR ")..tostring(res))
'''

def _lua_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

def _next_n() -> int:
    inbox = os.path.join(BRIDGE, "inbox")
    os.makedirs(inbox, exist_ok=True); os.makedirs(os.path.join(BRIDGE, "outbox"), exist_ok=True)
    ns = [int(m.group(1)) for f in os.listdir(inbox) for m in [re.match(r"cmd_(\d+)\.lua$", f)] if m]
    return max(ns, default=0) + 1

def _send(body: str, timeout: float = 600) -> str:
    n = _next_n()
    path = os.path.join(BRIDGE, "inbox", f"cmd_{n}.lua")
    code = PRELUDE.replace("@@N@@", str(n)).replace("@@ROOT@@", LUA_ROOT).replace("@@BODY@@", body)
    with open(path + ".tmp", "w") as f:
        f.write(code)
    os.rename(path + ".tmp", path)
    done = os.path.join(BRIDGE, "outbox", f"res_{n}.xml")
    t0 = time.time()
    while not os.path.exists(done):
        if time.time() - t0 > timeout:
            return f"TIMEOUT: no reply for cmd_{n}. Is bridge.lua running in Resolve's console?"
        time.sleep(0.3)
    time.sleep(0.2)
    parts, k = [], 1
    while os.path.exists(os.path.join(BRIDGE, "outbox", f"res_{n}_{k}.xml")):
        x = open(os.path.join(BRIDGE, "outbox", f"res_{n}_{k}.xml")).read()
        m = re.search(r"<name>__out__\d+~(.*?) \(Resolve\)</name>", x, re.S)
        parts.append(m.group(1) if m else "?")
        k += 1
    return "".join(parts)

@mcp.tool()
def bridge_status() -> str:
    """Check the bridge: returns Resolve version, project and current timeline."""
    return _send('local tl=p:GetCurrentTimeline() return "version="..r:GetVersionString()..";project="..p:GetName()..";timeline="..(tl and tl:GetName() or "none")', timeout=15)

@mcp.tool()
def run_lua(body: str, timeout: float = 600) -> str:
    """Run Lua inside Resolve. `body` is a function body that must `return` a string.
    In scope: r (resolve), pm, p (project), mp (media pool), bmd, fu. Keep results short-ish (chunked)."""
    return _send(body, timeout)

@mcp.tool()
def list_timelines() -> str:
    """List timelines in the current project."""
    return _send('local t={} for i=1,p:GetTimelineCount() do t[#t+1]=p:GetTimelineByIndex(i):GetName() end return table.concat(t,";")')

@mcp.tool()
def import_media(paths: list[str]) -> str:
    """Import files (absolute macOS paths) into the media pool root. Skips already-imported files."""
    arr = "{" + ",".join(_lua_str(p) for p in paths) + "}"
    return _send(f'''local want={arr} local have={{}}
for _,c in ipairs(mp:GetRootFolder():GetClipList()) do have[c:GetClipProperty("File Path")]=true end
local need={{}} for _,f in ipairs(want) do if not have[f] then need[#need+1]=f end end
local n=0 if #need>0 then local it=mp:ImportMedia(need) n=it and #it or 0 end
return "imported="..n..";already="..(#want-#need)''')

@mcp.tool()
def build_timeline(name: str, segments: list[dict], width: int = 1080, height: int = 1920, fps: int = 30) -> str:
    """Create a timeline and append clips in order.
    segments: [{"path": "/abs/file.mp4", "start": srcFrameIn, "end": srcFrameOut}] (source frames)."""
    rows = ",".join("{" + f'path={_lua_str(s["path"])},s={int(s["start"])},e={int(s["end"])}' + "}" for s in segments)
    return _send(f'''local segs={{{rows}}}
local by={{}} for _,c in ipairs(mp:GetRootFolder():GetClipList()) do by[c:GetClipProperty("File Path")]=c end
local need={{}} for _,s in ipairs(segs) do if not by[s.path] then need[#need+1]=s.path end end
if #need>0 then for _,it in ipairs(mp:ImportMedia(need) or {{}}) do by[it:GetClipProperty("File Path")]=it end end
local tl=mp:CreateEmptyTimeline({_lua_str(name)})
tl:SetSetting("useCustomSettings","1") tl:SetSetting("timelineResolutionWidth","{width}") tl:SetSetting("timelineResolutionHeight","{height}") tl:SetSetting("timelineFrameRate","{fps}") tl:SetSetting("timelineInputResMismatchBehavior","scaleToCrop")
p:SetCurrentTimeline(tl)
local infos={{}} for i,s in ipairs(segs) do infos[i]={{mediaPoolItem=by[s.path],startFrame=s.s,endFrame=s.e,trackIndex=1}} end
local items=mp:AppendToTimeline(infos)
for _,it in ipairs(items or {{}}) do it:SetProperty("Scaling", r.SCALE_FILL) end
return "timeline="..tl:GetName()..";items="..(items and #items or 0)''')

@mcp.tool()
def set_clip_zoom(timeline: str, index: int, zoom: float) -> str:
    """Zoom clip #index (1-based, video track 1) e.g. 1.8 to fill a vertical frame."""
    return _send(f'''local tl=nil for i=1,p:GetTimelineCount() do local t=p:GetTimelineByIndex(i) if t:GetName()=={_lua_str(timeline)} then tl=t end end
local it=tl:GetItemListInTrack("video",1)[{index}]
return "x="..tostring(it:SetProperty("ZoomX",{zoom}))..";y="..tostring(it:SetProperty("ZoomY",{zoom}))''')

@mcp.tool()
def add_text_card(timeline: str, index: int, line1: str, line2: str = "", band_alpha: float = 0.32,
                  font1: str = "Cormorant SC SemiBold", style1: str = "Regular", size1: float = 0.06,
                  font2: str = "Cormorant Garamond Light Medium", style2: str = "Italic", size2: float = 0.05) -> str:
    """Add a one- or two-line text card (centred mid-frame, soft dark band) to clip #index via a Fusion comp.
    Fonts must be installed on the Mac or the render fails."""
    return _send(f'''local tl=nil for i=1,p:GetTimelineCount() do local t=p:GetTimelineByIndex(i) if t:GetName()=={_lua_str(timeline)} then tl=t end end
local it=tl:GetItemListInTrack("video",1)[{index}]
local comp=it:GetFusionCompByIndex(1) or it:AddFusionComp()
local mi=comp:FindTool("MediaIn1") local mo=comp:FindTool("MediaOut1")
local bg=comp:AddTool("Background") bg:SetInput("TopLeftRed",0) bg:SetInput("TopLeftGreen",0) bg:SetInput("TopLeftBlue",0) bg:SetInput("TopLeftAlpha",{band_alpha})
local rm=comp:AddTool("RectangleMask") rm:SetInput("Width",1.3) rm:SetInput("Height",0.13) rm:SetInput("SoftEdge",0.06) rm:SetInput("Center",{{0.5,0.495}})
bg:ConnectInput("EffectMask",rm)
local last=comp:AddTool("Merge") last:ConnectInput("Background",mi) last:ConnectInput("Foreground",bg)
local function txt(str,font,style,size,y)
  local t=comp:AddTool("TextPlus") t:SetInput("StyledText",str) t:SetInput("Font",font) t:SetInput("Style",style) t:SetInput("Size",size) t:SetInput("Center",{{0.5,y}})
  local m=comp:AddTool("Merge") m:ConnectInput("Background",last) m:ConnectInput("Foreground",t) last=m
end
local l2={_lua_str(line2)}
if l2~="" then txt({_lua_str(line1)},{_lua_str(font1)},{_lua_str(style1)},{size1},0.512) txt(l2,{_lua_str(font2)},{_lua_str(style2)},{size2},0.474)
else txt({_lua_str(line1)},{_lua_str(font1)},{_lua_str(style1)},{size1},0.5) end
mo:ConnectInput("Input",last)
return "ok"''')

@mcp.tool()
def render(timeline: str, out_dir: str, name: str, fmt: str = "mp4", codec: str = "H264") -> str:
    """Render a timeline to out_dir/name. Returns job status and any error."""
    return _send(f'''local tl=nil for i=1,p:GetTimelineCount() do local t=p:GetTimelineByIndex(i) if t:GetName()=={_lua_str(timeline)} then tl=t end end
p:SetCurrentTimeline(tl) p:SetCurrentRenderFormatAndCodec({_lua_str(fmt)},{_lua_str(codec)})
p:SetRenderSettings({{TargetDir={_lua_str(out_dir)},CustomName={_lua_str(name)},SelectAllFrames=true}})
local job=p:AddRenderJob() p:StartRendering(job)
local t=0 while p:IsRenderingInProgress() and t<1200 do bmd.wait(0.5) t=t+1 end
local st=p:GetRenderJobStatus(job)
return "status="..tostring(st.JobStatus)..";pct="..tostring(st.CompletionPercentage)..";err="..tostring(st.Error)''', timeout=900)

@mcp.tool()
def stop_bridge() -> str:
    """Stop bridge.lua (it exits on its next poll)."""
    open(os.path.join(BRIDGE, "STOP"), "w").close()
    return "STOP written"

if __name__ == "__main__":
    mcp.run()
