# Viewer freeze investigation

Branch: `viewer/freeze-diagnostics`.

## Observations on pf-omen (2026-10-02)

- Windows viewer: `D:\Apps\TigerVNC\vncviewer.exe`, version 1.16.0.
- Viewer process 31608 was running and reported `Responding=True`.
  This only establishes that Windows could contact its window; it does not
  establish that framebuffer updates were arriving or being displayed.
- `TMP` and `TEMP` point to `D:\tmp`. No `vncviewer.log` existed there or in
  the account's usual temporary folder when checked.
- No TigerVNC events were returned by the Application event-log query for
  the preceding seven days. CIM process inspection was denied; ordinary
  `Get-Process` provided the executable and version.
- Stock viewer logging defaults to stderr. In version 1.16.0, the file
  logger uses the hard-coded `C:\temp\vncviewer.log`; the newer master source
  honors TMP. The original launcher incorrectly assumed stock 1.16.0 also
  honored TMP, so it displayed a session log path without producing a log.
  The corrected launcher creates `C:\temp` and copies the stock file log
  into the session folder while the viewer is running.

No cause has been established and the actual Mac freeze has not been
reproduced. The next step is to capture an affected session with timestamps,
including whether the Mac screen was changing while the viewer was frozen.

## Traffic meter

Enable **Options → Miscellaneous → Show incoming traffic meter**, or launch
with `-ShowStats`. The setting is saved with other viewer options.
The lower-right graph displays completed updates/s (green), pixels/s
(yellow), and incoming socket payload bits/s (red). It samples every 0.5 s.
It includes data already read into the socket buffer and TLS overhead;
it excludes TCP/IP overhead and outgoing traffic. Its counters are sampled
modulo 32 bits, so more than 4 GiB between samples would wrap.

The meter reuses the existing debug graph. Initial sample counters are now
seeded when it is enabled, and incoming rate arithmetic uses floating point
so multiplying by 1000 cannot overflow a 32-bit integer on a fast link.

## Capturing a session on Windows

Run `contrib/Start-ViewerDiagnostics.ps1` in PowerShell. It starts a new
connection dialog and creates a separate session folder under
`%LOCALAPPDATA%\TigerVNC\diagnostics`. The stock viewer gets persistent
logs and its existing debug traffic graph. It does not replace the installed
executable or interrupt an existing connection. A **TigerVNC Diagnostics**
desktop shortcut and a copy of the launcher at
`D:\Apps\TigerVNC\Start-ViewerDiagnostics.ps1` were installed on pf-omen.

With a Windows executable built from this branch, use:

```powershell
.\contrib\Start-ViewerDiagnostics.ps1 -ViewerPath 'C:\path\vncviewer.exe' -Instrumented
```

The instrumented build adds a `[ConnectionDiagnostics]` record every five
seconds, at normal log level:

- `interval_ms`: actual time between timer callbacks. Large gaps show a
  delayed event loop, system suspension, or a modal operation; they do not
  alone identify a cause. A blocked event loop cannot log until it resumes.
- `rx_bytes`: incoming socket payload bytes since the previous sample.
- `updates`: completed framebuffer updates since the previous sample.
- `last_update_ms`: time since completion, or session initialization if no
  update has completed yet. An unchanged remote screen may legitimately idle.
- `partial_update_ms`: age of an unfinished framebuffer update, or zero.
- `rx_buffered`: unread bytes in the socket stream, below TLS when used.
- `tx_buffered`: whether socket output is waiting to flush.
- `processing`: whether the asynchronous message timer is scheduled.
- `protocol_state`: the RFB connection state; normal is 7.
- `consumed_bytes`: cumulative position in the socket stream.

Message-processing callbacks taking at least one second also log their
elapsed time. Timing uses a monotonic clock. No screen contents, clipboard
contents, passwords, or key events are added to these diagnostics.

Record the freeze's clock time and preserve the session folder. A long
partial update with no incoming bytes is different evidence from incoming
bytes with no completed updates. A timer gap is different again. None of
these records treats an idle desktop as a proven freeze.

## Validation

`tests/integration/viewer-diagnostics.py` starts a loopback-only RFB server,
completes an update, idles, pauses an update midway, and resumes it. It runs
the real viewer with the meter enabled and checks diagnostics for all three
states and responsive timers:

```sh
DISPLAY=:91 python3 tests/integration/viewer-diagnostics.py build/vncviewer/vncviewer
```

Use an isolated X display (e.g. Xvfb) and the viewer's runtime libraries.
This validates the new instrumentation, not the reported Mac-specific bug.
A Windows build and an affected Mac session are still needed for that.

## Live zero-throughput observation (2026-10-02, approximately 23:15–23:18)

The user observed zero updates/s, zero pixels/s, and zero incoming bits/s
in the stock viewer's graph. Process 44096 reported responsive, with a TCP
connection from pf-omen to `10.0.2.11:5900` in ESTABLISHED state. A separate
unauthenticated connection to that endpoint received `RFB 003.889`.
Neither result establishes that the existing session is updating. The user
could not check the Mac's physical display, so an idle screen is not ruled
out. No cause has been established.

The launcher-created folder `20261002-230629-45728` contained no log file.
The 1.16.0 hard-coded log directory `C:\temp` was absent and was created
while the viewer was running, allowing later file-log messages to be saved
there. This cannot recover earlier messages. A test of redirected stderr produced an empty file with the installed
Windows GUI executable. A subsequent loopback connection-refusal test
verified that the stock file logger writes to `C:\temp` once that directory
exists. The corrected launcher creates that directory and copies each new
session's file log into its session folder every second. It also records
viewer responsiveness, CPU time, memory and TCP connection states every
five seconds in `connection-state.log`. These process samples do not prove
that framebuffer updates are arriving.

A new `TigerVNC Diagnostics v2` shortcut points to
`D:\Apps\TigerVNC\Start-ViewerDiagnostics-v2.ps1`. Close the old viewer
session before using it, and leave the launcher running while connected.

## Confirmed lack of visible response (2026-10-02, approximately 23:33)

Session `20261002-232637-26248` captured actual viewer logs successfully.
At zero throughput, clicking the Mac menu / moving over its Dock produced
no visible response or traffic, according to the user. The viewer remained
responsive and its TCP session remained ESTABLISHED across the report.
Its log had no disconnect or protocol error; the last entry was an automatic
quality adjustment at 23:29. At 23:35 a new unauthenticated connection still
received the Mac's `RFB 003.889` greeting. This rules out a complete failure
to accept new VNC connections, but does not prove the existing session's
network path, server update stream, or decoder is healthy.

Snapshots are stored locally in `build/diagnostics/20261002-2333` (excluded
from git). A Windows viewer build with the connection-progress diagnostics
is required to distinguish incomplete updates from lack of incoming data.
The Windows viewer diagnostics workflow packages the executable and its
runtime libraries separately from the installed stock viewer.

## Instrumented Windows viewer deployed

The Windows viewer build succeeded for commit `14e413f1` in workflow run
`37097327769`. The executable and its runtime DLLs are installed separately
at `D:\Apps\TigerVNC-Diagnostics\14e413f1`. A desktop shortcut named
**TigerVNC Instrumented Diagnostics** invokes the packaged launcher with
`-Instrumented` and the new executable path. The stock viewer was preserved.

Executable SHA256:
`ca9035286d4a79f2373a401eb29247596a42250be7784859ccc728603920f020`.

The real viewer integration test passed on pf-omen with the packaged Windows
executable: idle state, partial update with responsive UI timers, and update
completion on resumption were all recorded correctly. In that test, a paused
update logged `updates=0 partial_update_ms=4001` and its resumption logged
`updates=1 partial_update_ms=0`. This verifies the instrumentation, not a fix
for the real Mac session freeze.
