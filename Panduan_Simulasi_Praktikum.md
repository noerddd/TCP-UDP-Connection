# Panduan simulasi praktikum soket dan TLS

Panduan ini menggunakan kode dalam `kode_lab_chat_c_1/` pada Linux. Semua layanan mengikat `127.0.0.1`; lakukan pengujian hanya pada mesin lab sendiri. Gunakan terminal terpisah untuk server dan klien. Hentikan server dengan Ctrl+C setelah setiap modul.

## Persiapan

Diperlukan compiler C, Make, pthread, Python 3, OpenSSL beserta header pengembangannya, serta tcpdump dan sudo untuk capture. Dari direktori repositori:

```bash
cd kode_lab_chat_c_1
make all
make pki
```

Target Makefile menghasilkan nama executable yang lebih pendek daripada nama sumber. `make pki` membuat CA dan sertifikat lab, termasuk SAN `localhost` dan `127.0.0.1`, berlaku 30 hari. Jangan membuat ulang PKI ketika server sedang menggunakannya. Kunci privat dalam `pki/` hanya untuk lab.

## Modul 1 — server iteratif

Terminal server:

```bash
./s1_server 15101
```

Terminal A: jalankan `./s1_klien 15101 A`, kirim satu baris, kemudian biarkan terminal terbuka. Terminal B: jalankan `./s1_klien 15101 B` dan kirim satu baris. Tunggu dua detik, lalu tutup input klien A dengan Ctrl+D.

Catat waktu `connect()`, pengiriman, dan balasan B. Koneksi B dapat berhasil melalui antrean kernel, sementara balasan aplikasinya tertunda sampai A terputus. Server tertahan pada `recv()` A dan belum memanggil `accept()` berikutnya. Kriteria berhasil: echo B baru muncul setelah koneksi A berakhir.

## Modul 2 — polling

```bash
./s2_server 15102
```

Pada dua terminal lain jalankan `./s2_klien 15102 alice` dan `./s2_klien 15102 bob`. Kirim pesan bergantian, jalankan `/who`, lalu `/quit`. Pesan alice diterima bob dan sebaliknya; pengirim tidak menerima echo pesannya sendiri.

Periksa jumlah thread server dengan `ps -L -p PID_SERVER`. `poll()` menunggu kesiapan listener dan banyak soket sekaligus; satu thread memproses event yang siap secara bergantian. Ini konkurensi I/O, bukan eksekusi CPU paralel. Kode modul 2 masih memakai `send()` blocking, sehingga pembaca lambat dapat menahan event loop. Kriteria berhasil: dua koneksi tetap aktif dan dapat bertukar pesan tanpa menunggu klien lain terputus.

## Modul 3 — byte stream dan inspeksi header

**Koreksi terhadap ketentuan:** `s3_server_mentah.c` menggunakan `socket(AF_INET, SOCK_STREAM, 0)`, bukan `SOCK_RAW`. Nama “mentah” merujuk payload yang belum dirakit menjadi baris. Menjalankannya dengan sudo tidak membuat header TCP/UDP tersedia di `recv()`. `s3_pengirim.c` hanya mengirim TCP.

Untuk memenuhi perintah eksekusi root pada mesin yang memiliki sudo, jalankan:

```bash
sudo ./s3_server 15103
```

Pada terminal lain:

```bash
./s3_pengirim 15103
```

Catat banyaknya `recv()`, ukuran setiap pembacaan, dan jumlah byte. Tiga pesan pendek berjumlah 32 byte, diikuti 200001 byte; totalnya 200033 byte. Batas `send()` tidak dipertahankan oleh TCP. Pembagian pembacaan boleh berbeda antarpercobaan.

Untuk melihat header jaringan sebenarnya, mulai capture **sebelum** mengulang server dan pengirim:

```bash
sudo tcpdump -i lo -nn -s 0 -U -w /tmp/modul3.pcap 'tcp port 15103 or udp port 15133'
```

Tambahkan trafik UDP lokal melalui Python pada terminal lain:

```bash
python3 - <<'PY'
import socket
receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
receiver.bind(('127.0.0.1', 15133))
sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sender.sendto(b'UDP-LAB', ('127.0.0.1', 15133))
print(receiver.recvfrom(1024))
sender.close()
receiver.close()
PY
```

Hentikan tcpdump dengan Ctrl+C lalu baca:

```bash
sudo tcpdump -nn -vvv -X -r /tmp/modul3.pcap
```

Identifikasi alamat IP, protocol IP 6/TCP dan 17/UDP, port sumber/tujuan, sequence/acknowledgment dan flags TCP, panjang header TCP (data offset), serta length UDP. Payload UDP contoh 7 byte berarti UDP length 15 byte, termasuk header 8 byte. Jangan menyamakan satu `recv()` aplikasi dengan satu paket hasil capture. Capture memerlukan izin root/capability; tanpa izin tersebut, hasil inspeksi header harus ditandai belum terverifikasi.

## Modul 4 — klien lambat dan latensi

Server dengan send buffer kecil agar backpressure mudah terlihat:

```bash
./s4_server 15104 1024
```

Secara bersamaan jalankan:

```bash
./s4_lambat 15104 lambat 20
./s4_probe 15104 probe 8
```

Klien lambat mendaftar lalu tidak membaca; tanpa siaran yang cukup banyak, kondisi ini belum tentu menekan resource. Tambahkan beberapa pengirim normal, masing-masing mengirim baris kurang dari 2048 byte dan paling banyak 10 baris per detik. Skrip otomatis di bawah memakai empat pengirim, masing-masing 64 pesan sepanjang 1801 byte dengan jeda sedikitnya 130 ms, sambil membaca balasannya.

Amati log `antrean_penuh(65536 byte)`, pemutusan klien lambat, dan balasan probe yang tetap tersedia. Server menggunakan soket nonblocking, antrean output terbatas, rate limit, dan timeout. Probe bawaan mengukur kedatangan data apa pun, sehingga siaran atau salam juga dapat terhitung sebagai balasan. Skrip otomatis menambahkan koneksi yang memeriksa keberadaan `klien=` dari `/stat` untuk mengukur respons aplikasi secara lebih spesifik. Angka ini tetap dipengaruhi beban dan penjadwalan mesin lokal.

## Modul 5 — thread per koneksi dan memori

Implementasi sudah tersedia di `s5_server_thread.c`: `pthread_create()` membuat thread untuk setiap koneksi, `pthread_detach()` melepas resource thread setelah berakhir, dan mutex melindungi daftar bersama. Makefile menambahkan `-pthread`.

```bash
./s5_server 15106
```

Hubungkan dua `s2_klien` pada port 15106 untuk bertukar pesan; `/stat` melaporkan jumlah koneksi. Bandingkan dengan `s2_server` menggunakan proses baru untuk setiap beban 0, 8, dan 24 koneksi. Keduanya membatasi klien pada 32. Baca `VmSize`, `VmRSS`, dan `Threads` dari `/proc/PID/status` sebelum dan sesudah beban.

`VmSize` adalah ruang alamat virtual (termasuk reservasi stack thread), sedangkan `VmRSS` adalah halaman resident. Jangan menyebut VmSize sebagai RAM yang seluruhnya terpakai. Uji ini membandingkan jejak memori, bukan mengukur kecepatan `malloc()` atau throughput. Mutex dan penulisan blocking juga dapat membatasi skalabilitas modul 5 ketika ada pembaca lambat.

## Modul 6 — TLS dan penolakan plaintext

```bash
./s6_server 15443 pki/server.crt pki/server.key
```

Terminal klien dan probe:

```bash
./s6_klien 15443 pki/ca.crt aman
./s6_probe 15443 pki/ca.crt probeTLS 3
```

Kirim `/tls` pada klien untuk melihat versi dan cipher; klien memverifikasi CA serta identitas `localhost`. `s6_probe_tls.c` adalah **probe TLS**, bukan pengirim plaintext. Karena itu, uji penolakan plaintext dilakukan terpisah:

```bash
python3 - <<'PY'
import socket
with socket.create_connection(('127.0.0.1', 15443), timeout=3) as s:
    s.sendall(b'GET / HTTP/1.0\r\n\r\n')
    try:
        print(repr(s.recv(1024)))
    except ConnectionResetError:
        print('koneksi di-reset server')
PY
```

Kriteria berhasil: koneksi TLS terverifikasi berhasil, `/tls` mendapat respons, dan plaintext ditutup/reset dengan log kegagalan handshake. Penolakan plaintext saja tidak membuktikan seluruh keamanan TLS atau keamanan endpoint.

## Menjalankan ulang simulasi otomatis

Dari root repositori, setelah kompilasi dan pembuatan PKI:

```bash
python3 simulasi_praktikum.py
```

Skrip menggunakan port 15101–15106 dan 15443, berjalan sekitar satu menit, mencatat log dan `ringkasan.json` dalam `hasil_simulasi/`, lalu menghentikan proses miliknya. Pastikan port tersebut kosong. Eksekusi berikutnya menimpa hasil lama. Simulasi otomatis menjalankan modul 3 sebagai server TCP biasa; capture/root dijalankan manual sesuai langkah di atas. Pembatasan sandbox dapat memerlukan izin eksekusi jaringan lokal di luar sandbox, yang berbeda dari hak root sistem operasi.
