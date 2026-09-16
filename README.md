# The Closet Club
PBP midterm project - Slow Fashion & Conscious Shopping

# Deskripsi Aplikasi
The Closet Club (TCC) adalah platform komunitas fashion berbasis media sosial yang mendorong penerapan slow fashion dan conscious shopping. Pengguna dapat membagikan outfit melalui feed sebagai inspirasi, mencatat koleksi pakaian dalam digital closet, serta menandai pakaian tertentu yang tersedia untuk dibarter, ditukar tambah, atau ditawarkan kepada pengguna lain. Setiap post outfit dapat mencantumkan daftar pakaian yang digunakan. Jika pengguna lain tertarik pada salah satu item dalam outfit tersebut, mereka dapat memilih item itu dan diarahkan ke digital closet milik pengunggah untuk melihat detail pakaian dan ketersediaannya. Pengguna juga dapat berkomunikasi melalui fitur chat untuk mendiskusikan kondisi, ukuran, maupun kesepakatan sebelum melakukan pertukaran.

# Manfaat Bagi Masyarakat
1. Memperpanjang usia pakai pakaian dan mengurangi limbah tekstil.
2. Memudahkan orang menemukan pakaian secondhand/thrift yang mereka butuhkan tanpa harus membeli baru.
3. Membangun komunitas yang peduli terhadap sustainable living.

# Target Pengguna
1. Orang yang tertarik dengan barang secondhand/thrift.
2. Pemilik pakaian yang sudah jarang dipakai.
3. Orang yang peduli dengan sustainable living.

# Anggota Kelompok
Nama - NPM - Modul yang Dikerjakan
1. Ria Lavenia Kharissa - 2506543905 - Login, Profile & Reputation
2. Nauval Adiva Daneshwara - 2506623074 - Feed & Clothing Post
3. Nadya Alyssa Azzahra - 2506599270 - My Closet
4. Faiz Yusuf Elriki - 2506607921 - Chat
5. Naila Husna Teguh Suasono - 2506620444 - Swap / Barter

# Daftar Modul
1. Login, Profile, & Reputation
   fungsi: User bisa daftar, login, punya profil, mendapat badge verifikasi, serta rating/review dari hasil barter
   frontend: Halaman login/register, profile, edit profile, badge verified, tampilan rating & review
   backend/database: 'users' (akun, username, foto profil, status verifikasi), 'verifications', 'reviews' (status verifikasi & rating user)

2. Feed & Clothing Post
   fungsi: User bisa upload dan melihat pakaian orang lain seperti feed sosmed
   frontend: Feed, card pakaian, search/filter, halaman detail, tombol "Interested"
   backend/database: 'clothes' (nama, foto, ukuran, kondisi, deskripsi, pemilik, status)

3. My Closet
   fungsi: User mengelola pakaian yang dia punya/tawarkan
   frontend: Halaman "My Closet", tambah/edit/hapus pakaian
   backend/database: CRUD data clothes milik user

4. Chat
   fungsi: User dan pemilik pakaian bisa ngobrol sebelum barter
   frontend: Chat list, chat room, kirim pesan
   backend/database: 'conversations' + 'messages' (pengirim, penerima, isi pesan, waktu)

5. Swap / Barter
   fungsi: Kalau sudah sepakat, user membuat request barter
   frontend: Pilih barang → ajukan swap → accept/reject → status barter
   backend/database: 'swap_requests' (siapa menukar apa dengan apa, status request)

# Public / Mock API
OpenStreetMap, menghitung titik temu rekomendasi di antara dua pengguna yang sedang bersepakat untuk barter pakaian, serta memfilter lokasi fasilitas umum terdekat yang aman (seperti stasiun atau minimarket) untuk proses serah-terima barang.

Dokumentasi:
1. https://wiki.openstreetmap.org/wiki/API
2. https://taginfo.openstreetmap.org/taginfo/apidoc

# Figma
Design: https://www.figma.com/team_invite/redeem/KOtMSHkQUlfOvsd0sgdnDd?t=FXv8TF02EvT69n4W-21

# Jenis / Peran Pengguna
1. Guest (Belum Login)
   Hak akses: Hanya baca (read-only) pada konten publik.
   Bisa: Menjelajahi feed outfit inspirasi, melihat katalog pakaian publik di closet orang lain, menggunakan fitur pencarian/filter.
   Tidak bisa: Mengunggah outfit, menambah pakaian ke closet, mengakses chat, mengajukan barter, memberikan ulasan.

2. Registered User (Sudah Login)
   Hak akses: Semua hak Guest, ditambah kemampuan berinteraksi penuh.
   Bisa: Upload outfit ke feed, menambah pakaian ke My Closet, chat dengan user lain, mengajukan swap/barter.
   
