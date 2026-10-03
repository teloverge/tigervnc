#!/usr/bin/env python3
"""Exercise the real viewer with idle, incomplete and resumed RFB updates.

Run with an isolated X display, e.g. DISPLAY=:91 python3 this-file viewer-path.
This validates diagnostics; it does not reproduce the reported Mac freeze.
"""
import argparse
import os
import re
import socket
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path


def receive(sock, length):
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise EOFError('viewer disconnected')
        data.extend(chunk)
    return bytes(data)


def serve(listener, errors):
    try:
        with listener.accept()[0] as client:
            client.settimeout(10)
            client.sendall(b'RFB 003.008\n')
            receive(client, 12)
            client.sendall(b'\x01\x01')  # None authentication, loopback only
            assert receive(client, 1) == b'\x01'
            client.sendall(struct.pack('>I', 0))
            receive(client, 1)
            name = b'Diagnostics test'
            fmt = struct.pack('>BBBBHHHBBBxxx', 32, 24, 0, 1,
                              255, 255, 255, 16, 8, 0)
            client.sendall(struct.pack('>HH', 640, 480) + fmt +
                           struct.pack('>I', len(name)) + name)
            while True:
                msg = receive(client, 1)[0]
                if msg == 0:  # SetPixelFormat
                    receive(client, 19)
                elif msg == 2:  # SetEncodings
                    count = struct.unpack('>xH', receive(client, 3))[0]
                    receive(client, count * 4)
                elif msg == 3:  # FramebufferUpdateRequest
                    receive(client, 9)
                    break
                else:
                    raise AssertionError(f'unexpected client message {msg}')
            header = struct.pack('>BBHHHHHi', 0, 0, 1, 0, 0, 640, 480, 0)
            pixels = b'\x80\x40\x20\x00' * (640 * 480)
            client.sendall(header + pixels)
            time.sleep(6)  # complete update followed by idle
            client.sendall(header + pixels[:128])
            time.sleep(6)  # unfinished update; UI timer must keep running
            client.sendall(pixels[128:])
            time.sleep(4)  # resumed update must complete
    except Exception as error:
        errors.append(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('viewer')
    parser.add_argument('--screenshot', help='Optional screenshot path (requires Pillow)')
    args = parser.parse_args()
    viewer = str(Path(args.viewer).resolve())
    errors = []
    with socket.socket() as listener, tempfile.TemporaryDirectory() as tmp:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        worker = threading.Thread(target=serve, args=(listener, errors), daemon=True)
        worker.start()
        log_path = Path(tmp) / 'viewer.log'
        env = dict(os.environ, XDG_CONFIG_HOME=tmp, XDG_STATE_HOME=tmp,
                   XDG_DATA_HOME=tmp)
        with log_path.open('w') as log:
            process = subprocess.Popen([
                viewer, '-ShowStats', '-ConnectionDiagnostics',
                '-SecurityTypes', 'None', '-AutoSelect=0', '-RemoteResize=0',
                '-AlertOnFatalError=0', '-ReconnectOnError=0',
                f'127.0.0.1::{listener.getsockname()[1]}',
            ], env=env, stdout=log, stderr=log)
            try:
                if args.screenshot:
                    from PIL import ImageGrab
                    time.sleep(2)
                    assert process.poll() is None, 'viewer exited before capture'
                    screenshot = ImageGrab.grab(xdisplay=env['DISPLAY'])
                    screenshot.save(args.screenshot)
                worker.join(22)
                assert not worker.is_alive(), 'test server timed out'
                assert not errors, errors
                process.wait(timeout=5)
                assert process.returncode == 0, process.returncode
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
        text = ' '.join(log_path.read_text().split())
        records = re.findall(r'\[ConnectionDiagnostics\] interval_ms=(\d+) '
                             r'rx_bytes=(\d+) updates=(\d+) last_update_ms=(\d+) '
                             r'partial_update_ms=(\d+)', text)
        assert len(records) >= 3, text
        idle, partial, resumed = [tuple(map(int, row)) for row in records[:3]]
        assert idle[2] == 1 and idle[4] == 0, records
        assert partial[2] == 0 and partial[4] >= 2000, records
        assert partial[1] > 0, records
        assert resumed[2] == 1 and resumed[4] == 0 and resumed[1] > 0, records
        assert all(4000 <= row[0] <= 6500 for row in (idle, partial, resumed)), records
        print('PASS: idle, partial update, resumed update; UI timers stayed active')
        for row in records:
            print('interval_ms=%s rx_bytes=%s updates=%s last_update_ms=%s partial_update_ms=%s' % row)


if __name__ == '__main__':
    main()
