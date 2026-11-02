# Laporan hasil simulasi praktikum

Pelaksanaan: 1 November 2026, mulai 12:29:35 WIB (05:29:35 UTC). Platform: Linux 6.17.0-41-generic, x86_64, glibc 2.42. Seluruh trafik pengujian berada di `127.0.0.1`. Sumber C asli digunakan tanpa perubahan. Implementasi thread per koneksi telah tersedia dalam kode modul 5.

## Metode dan bukti

Semua 13 executable berhasil dikompilasi dengan Makefile (`-Wall -Wextra -O2`, tambahan pthread/OpenSSL sesuai target), tanpa peringatan compiler yang terlihat. `make pki` menghasilkan sertifikat lab dan verifikasi `server.crt: OK`. Sertifikat berlaku 1 November–1 Desember 2026 dan mencantumkan SAN localhost/127.0.0.1.

Pengujian dijalankan melalui [simulasi_praktikum.py](simulasi_praktikum.py). Angka pengukuran tersimpan dalam [ringkasan.json](hasil_simulasi/ringkasan.json), sedangkan stdout/stderr program tersedia di [direktori hasil](hasil_simulasi/). Port modul 1–5: 15101–15106; TLS: 15443. Proses server dan klien milik simulasi telah dihentikan setelah pengujian.

Sandbox awal menolak pembuatan soket (`Operation not permitted`); simulasi berhasil dijalankan setelah memperoleh izin eksekusi di luar sandbox. Izin tersebut tidak memberikan hak root. Percobaan sudo di luar sandbox gagal dengan `interactive authentication is required`; tcpdump juga menolak capture dengan `You don't have permission ... (socket: Operation not permitted)`.

## Modul 1 — blocking I/O terbukti

Klien A dan B menggunakan `s1_klien`. A mengirim pesan dan mempertahankan koneksi; B lalu mengirim pesan saat A masih aktif.

| Peristiwa klien B | Waktu sejak klien B dimulai |
|---|---:|
| `connect()` berhasil | 0,6 ms |
| Pesan dikirim | 1,5 ms |
| Echo diterima setelah A diputus | 2000,3 ms |

Sebelum A ditutup, log B hanya berisi keberhasilan koneksi dan pengiriman, tanpa balasan. Koneksi TCP B dapat terbentuk di antrean kernel, tetapi server baru melayaninya setelah keluar dari loop `recv()` A. Ini membuktikan pelayanan aplikasi sekuensial, dengan penundaan sekitar dua detik yang sengaja diberikan oleh skenario uji.

Bukti: [klien A](hasil_simulasi/m1_A.log), [klien B](hasil_simulasi/m1_B.log), [server](hasil_simulasi/s1_server.log).

## Modul 2 — beberapa klien, satu thread

Alice dan bob terhubung bersamaan dengan `s2_klien`; masing-masing menerima pesan klien lainnya saat kedua koneksi tetap terbuka. Log alice memuat `[bob] halo dari bob`; log bob memuat `[alice] halo dari alice`. Snapshot server menunjukkan `Threads: 1`, VmSize 2980 KiB, dan VmRSS 2036 KiB.

Hasil ini sesuai dengan event loop `poll()`: server memproses soket yang siap tanpa menunggu koneksi lain berakhir. Penanganan tetap bergantian dalam satu thread. Pengujian tidak membuktikan ketahanan terhadap slow reader pada modul 2, karena jalur pengirimannya masih blocking.

Bukti: [alice](hasil_simulasi/m2_alice.log), [bob](hasil_simulasi/m2_bob.log), dan snapshot pada ringkasan JSON.

## Modul 3 — byte stream berhasil; inspeksi header belum terverifikasi

`s3_server` dan `s3_pengirim` berhasil dijalankan sebagai pengguna biasa. Server mencatat 52 panggilan `recv()` dan total **200033 byte**. Tiga pembacaan pertama berukuran 11, 10, dan 11 byte; pembacaan berikutnya memecah payload besar ke banyak potongan, sebagian besar 4096 byte, dengan potongan akhir 3393 byte.

Pengiriman payload besar tidak dipertahankan sebagai satu pembacaan. Pada percobaan ini tiga pesan kecil terbaca terpisah; penggabungan pesan kecil tidak teramati dan tidak boleh diasumsikan dari hasil ini. Ukuran pembacaan dapat berubah pada eksekusi ulang.

Ada ketidaksesuaian mendasar dengan spesifikasi: `s3_server_mentah.c` menggunakan `SOCK_STREAM`, sehingga `recv()` hanya memberikan payload TCP. Kode tidak menggunakan raw socket, tidak mem-parsing header transport, dan tidak melayani UDP. `s3_pengirim.c` juga hanya mengirim TCP. Menjalankan kode yang sama sebagai root tidak mengubah perilaku tersebut.

Eksekusi root melalui sudo dan penangkapan header TCP/UDP **belum terlaksana** karena akses root/capture tidak tersedia. Tidak ada pcap atau hasil analisis header aktual yang diklaim. Panduan pertama menyediakan langkah capture TCP dan trafik UDP tambahan untuk melanjutkannya pada mesin dengan izin yang sesuai.

Bukti byte stream: [server](hasil_simulasi/s3_server.log), [pengirim](hasil_simulasi/m3_pengirim.log).

## Modul 4 — server tetap responsif saat antrean klien lambat penuh

Server dijalankan dengan send buffer 1024 byte. `s4_lambat` mendaftar sebagai `lambat`, mengecilkan receive buffer, dan tidak membaca. Empat koneksi tambahan masing-masing mengirim 64 baris sepanjang 1801 byte dengan jeda sedikitnya 130 ms, sambil membaca trafik masuk. `s4_probe` berjalan bersamaan; koneksi normal tambahan memvalidasi isi respons `/stat`.

Log server pukul 05:29:46 UTC mencatat:

```text
PUTUS ... nama=lambat alasan=antrean_penuh(65536 byte)
KELUAR ... nama=lambat alasan=penutupan paksa sisa_antrean=64967
```

Batas terlampaui ketika pesan berikutnya akan ditambahkan, sehingga antrean tersisa bisa lebih kecil dari 65536 byte. Klien lambat diputus, sementara server terus merespons koneksi normal.

| Pengukuran | Hasil |
|---|---|
| Probe bawaan | 8 balasan, maksimum 0,8 ms, tanpa timeout |
| `/stat` dengan pemeriksaan `klien=` | 8/8 berhasil |
| Rentang latensi `/stat` tervalidasi | 0,59–1,20 ms |

Probe bawaan menganggap data apa pun sebagai respons; pada beban siaran, angkanya bukan RTT `/stat` yang pasti. Pemeriksaan tambahan menunggu `klien=` dan karena itu memberi bukti lebih spesifik bahwa permintaan aplikasi dilayani. Ini satu percobaan lokal terbatas, bukan jaminan latensi pada jaringan nyata atau serangan skala besar. Baris `socket error`/`gagal kirim` di akhir log terjadi ketika koneksi penguji ditutup dalam pembersihan.

Bukti: [probe](hasil_simulasi/m4_probe.log), [klien lambat](hasil_simulasi/m4_lambat.log), [server](hasil_simulasi/s4_server.log), dan delapan latensi tambahan di ringkasan JSON.

## Modul 5 — perbandingan jejak memori

Implementasi `s5_server_thread.c` memakai `pthread_create()` per koneksi dan `pthread_detach()`, dengan mutex untuk state bersama. Uji memakai proses baru pada setiap titik beban agar hasil tidak tercampur cache stack dari titik sebelumnya. Jumlah koneksi, nama, jeda pembukaan, dan waktu stabilisasi disamakan. Pada beban 8 dan 24 koneksi, skrip juga mengonfirmasi satu pesan dari klien terakhir sampai ke klien pertama pada kedua server.

| Arsitektur | Klien | Thread | VmSize (KiB) | VmRSS (KiB) |
|---|---:|---:|---:|---:|
| Polling | 0 | 1 | 2980 | 2032 |
| Polling | 8 | 1 | 2980 | 2048 |
| Polling | 24 | 1 | 2980 | 2084 |
| Thread per koneksi | 0 | 1 | 2912 | 2032 |
| Thread per koneksi | 8 | 9 | 68480 | 2128 |
| Thread per koneksi | 24 | 25 | 199616 | 2320 |

Pada 24 koneksi, VmSize server thread meningkat 196704 KiB terhadap baseline prosesnya, setara 8196 KiB per koneksi. Ini konsisten dengan reservasi stack thread beserta overhead, tetapi ukuran stack tidak diukur langsung. VmRSS meningkat hanya 292 KiB terhadap baseline proses yang sama (2028 KiB). Polling meningkat 48 KiB VmRSS dari baseline prosesnya (2036 KiB) tanpa pertumbuhan VmSize pada snapshot ini.

Dengan demikian, polling lebih hemat ruang alamat dan halaman resident pada beban yang diuji. Besarnya VmSize tidak berarti seluruhnya menggunakan RAM fisik. Angka `setup_ms` dalam JSON mencakup jeda buatan dan stabilisasi; angka itu tidak digunakan sebagai benchmark alokasi memori. Tidak ada pengukuran kecepatan malloc, throughput, atau generalisasi performa CPU dari uji ini. Satu percobaan per titik dan variasi RSS antarproses membatasi presisi kesimpulan.

Bukti utama: snapshot baseline dan loaded pada [ringkasan JSON](hasil_simulasi/ringkasan.json). Log server polling/thread disimpan untuk titik terakhir, yaitu 24 koneksi.

## Modul 6 — TLS berhasil dan plaintext ditolak

`s6_klien` berhasil memverifikasi sertifikat dan bernegosiasi **TLSv1.3**, cipher **TLS_AES_256_GCM_SHA384**. Perintah `/tls` mendapat respons dengan parameter yang sama. Klien keluar dengan kode 0.

`s6_probe` berhasil menjalankan tiga pengukuran terenkripsi: 0,8 ms, 1,0 ms, dan 0,6 ms; kode keluar 0. Sebagaimana probe modul 4, angka bawaan ini mengukur kedatangan data dan tidak memeriksa bahwa setiap balasan khusus berasal dari `/stat`.

Karena `s6_probe_tls.c` memang memakai TLS, pengujian plaintext memakai koneksi TCP Python terpisah yang mengirim `GET / HTTP/1.0`. Klien menerima `ConnectionResetError`. Server mencatat `TLS-GAGAL`, kesalahan `SSL routines::http request`, dan penutupan dengan alasan `handshake gagal`. Kedua sisi membuktikan penolakan HTTP plaintext pada listener TLS dalam skenario ini.

Bukti: [klien TLS](hasil_simulasi/m6_klien.log), [probe TLS](hasil_simulasi/m6_probe.log), [server TLS](hasil_simulasi/s6_server.log), dan hasil plaintext pada ringkasan JSON.

## Status pencapaian

Modul 1, 2, 4, 5, dan 6 telah diuji sesuai tujuan utamanya. Modul 3 berhasil menunjukkan perilaku byte stream TCP, tetapi bagian eksekusi root dan inspeksi header TCP/UDP masih memerlukan pelaksanaan pada mesin yang menyediakan akses sudo/capture. Panduan mencantumkan koreksi perilaku kode dan langkah lanjutan tersebut secara terpisah dari hasil yang sudah teramati.
