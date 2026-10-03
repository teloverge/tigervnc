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
- Stock viewer logging defaults to stderr. A file logger is available, but
  must be selected with `-Log '*:file:30'` to retain session records.

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
