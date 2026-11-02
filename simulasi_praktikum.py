#!/usr/bin/env python3
"""Simulasi lokal terbatas; jalankan dari root repositori setelah make all pki."""
import json, os, platform, socket, subprocess as sp, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAB = ROOT / 'kode_lab_chat_c_1'
OUT = ROOT / 'hasil_simulasi'
OUT.mkdir(exist_ok=True)
results = {'environment': {'date': time.strftime('%Y-%m-%d %H:%M:%S %z'), 'platform': platform.platform()}}
children = []

def start(binary, args, log):
    f = open(OUT / log, 'w')
    p = sp.Popen([str(LAB / binary), *map(str, args)], cwd=LAB, stdin=sp.PIPE, stdout=f, stderr=sp.STDOUT)
    f.close()
    children.append(p)
    return p

def stop(p):
    if p.poll() is None:
        p.terminate()
        try: p.wait(3)
        except sp.TimeoutExpired: p.kill(); p.wait()

def server(binary, port, extra=()):
    p = start(binary, [port, *extra], binary + '.log')
    time.sleep(.4)
    assert p.poll() is None, binary + ' gagal; periksa log'
    return p

def connect(port):
    return socket.create_connection(('127.0.0.1', port), timeout=3)

def drain(s):
    s.settimeout(.03)
    try:
        while s.recv(65536): pass
    except socket.timeout: pass

def status(pid):
    d = {}
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        k, _, v = line.partition(':')
        if k in ('VmSize', 'VmRSS', 'Threads'): d[k] = int(v.split()[0])
    return d

try:
    # A tetap terhubung sementara B menunggu echo.
    p = server('s1_server', 15101)
    a = start('s1_klien', [15101, 'A'], 'm1_A.log')
    a.stdin.write(b'pesan A\n'); a.stdin.flush(); time.sleep(.3)
    b = start('s1_klien', [15101, 'B'], 'm1_B.log')
    t = time.monotonic(); b.stdin.write(b'pesan B\n'); b.stdin.flush()
    time.sleep(2)
    before = (OUT / 'm1_B.log').read_text()
    a.stdin.close(); a.wait(4)
    b.stdin.close(); b.wait(4)
    results['m1'] = {'B_before_A_closed': before, 'elapsed_seconds': time.monotonic()-t, 'B_after': (OUT/'m1_B.log').read_text()}
    stop(p)

    p = server('s2_server', 15102)
    a = start('s2_klien', [15102, 'alice', 3], 'm2_alice.log')
    b = start('s2_klien', [15102, 'bob', 3], 'm2_bob.log')
    time.sleep(.4)
    a.stdin.write(b'halo dari alice\n'); a.stdin.flush()
    b.stdin.write(b'halo dari bob\n'); b.stdin.flush()
    time.sleep(.4)
    results['m2'] = {'server': status(p.pid)}
    a.wait(5); b.wait(5); stop(p)

    p = server('s3_server', 15103)
    c = start('s3_pengirim', [15103], 'm3_pengirim.log'); c.wait(6); p.wait(6)
    results['m3'] = {'stream_server_exit': p.returncode}

    # Paksa backpressure dengan send buffer kecil dan 4 pengirim di bawah rate limit.
    p = server('s4_server', 15104, [1024])
    slow = start('s4_lambat', [15104, 'lambat', 12], 'm4_lambat.log')
    probe = start('s4_probe', [15104, 'probe', 8], 'm4_probe.log')
    senders = []
    for i in range(4):
        s = connect(15104); s.sendall(f'banjir{i}\n'.encode()); senders.append(s)
    def flood(s):
        for _ in range(64):
            try: s.sendall(b'X'*1800+b'\n'); drain(s)
            except OSError: break
            time.sleep(.13)
    workers = [threading.Thread(target=flood, args=(s,)) for s in senders]
    for w in workers: w.start()
    # Klien normal tambahan memvalidasi isi /stat; probe bawaan menerima data apa pun.
    normal = connect(15104); normal.sendall(b'validasi\n'); time.sleep(.1); drain(normal)
    measurements = []
    for _ in range(8):
        drain(normal); t = time.monotonic(); normal.sendall(b'/stat\n'); data = b''; normal.settimeout(3)
        while b'klien=' not in data: data += normal.recv(65536)
        measurements.append((time.monotonic()-t)*1000); time.sleep(.8)
    for w in workers: w.join()
    probe.wait(5)
    results['m4'] = {'validated_stat_ms': measurements}
    normal.close()
    for s in senders: s.close()
    stop(slow); stop(p)

    # Beban sama, proses baru pada setiap titik untuk menghindari cache stack.
    memory = []
    for binary, port in [('s2_server', 15105), ('s5_server', 15106)]:
        for n in (0, 8, 24):
            p = server(binary, port); baseline = status(p.pid); clients = []
            t = time.monotonic()
            for i in range(n):
                s = connect(port); s.sendall(f'user{i}\n'.encode()); clients.append(s); time.sleep(.015)
            time.sleep(.25)
            snapshot = status(p.pid)
            memory.append({'binary': binary, 'clients': n, 'baseline': baseline, 'loaded': snapshot, 'setup_ms': (time.monotonic()-t)*1000})
            if n:
                clients[-1].sendall(b'pesan pembanding\n'); time.sleep(.1)
                clients[0].settimeout(2); data = b''
                while b'pesan pembanding' not in data: data += clients[0].recv(65536)
            for s in clients: s.close()
            stop(p)
    results['m5'] = memory

    p = server('s6_server', 15443, ['pki/server.crt', 'pki/server.key'])
    c = start('s6_klien', [15443, 'pki/ca.crt', 'aman', 3], 'm6_klien.log')
    c.stdin.write(b'/tls\n'); c.stdin.flush(); c.wait(6)
    probe = start('s6_probe', [15443, 'pki/ca.crt', 'probeTLS', 3], 'm6_probe.log'); probe.wait(8)
    s = connect(15443); s.sendall(b'GET / HTTP/1.0\r\n\r\n'); s.settimeout(3)
    try: reply = repr(s.recv(1024))
    except ConnectionResetError: reply = 'ConnectionResetError'
    s.close()
    results['m6'] = {'client_exit': c.returncode, 'tls_probe_exit': probe.returncode, 'plaintext_reply': reply}
    stop(p)
finally:
    for p in children: stop(p)
    (OUT / 'ringkasan.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
