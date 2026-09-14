# the-closet-club
pbp midterm project - Slow Fashion & Conscious Shopping

# deskripsi aplikasi
The Closet Club (TCC) adalah platform komunitas fashion berbasis media sosial yang mendorong penerapan slow fashion dan conscious shopping. Pengguna dapat membagikan outfit melalui feed sebagai inspirasi, mencatat koleksi pakaian dalam digital closet, serta menandai pakaian tertentu yang tersedia untuk dibarter, ditukar tambah, atau ditawarkan kepada pengguna lain. Setiap post outfit dapat mencantumkan daftar pakaian yang digunakan. Jika pengguna lain tertarik pada salah satu item dalam outfit tersebut, mereka dapat memilih item itu dan diarahkan ke digital closet milik pengunggah untuk melihat detail pakaian dan ketersediaannya. Pengguna juga dapat berkomunikasi melalui fitur chat untuk mendiskusikan kondisi, ukuran, maupun kesepakatan sebelum melakukan pertukaran.

# manfaat bagi masyarakat
1. Memperpanjang usia pakai pakaian dan mengurangi limbah tekstil.
2. Memudahkan orang menemukan pakaian secondhand/thrift yang mereka butuhkan tanpa harus membeli baru.
3. Membangun komunitas yang peduli terhadap sustainable living.

# target pengguna
1. Orang yang tertarik dengan barang secondhand/thrift.
2. Pemilik pakaian yang sudah jarang dipakai.
3. Orang yang peduli dengan sustainable living.

# anggota kelompok
nama - npm - modul yang dikerjakan
Ria Lavenia Kharissa - 2506543905 - Login, Profile & Reputation
Nauval Adiva Daneshwara - 2506623074 - Feed & Clothing Post
Nadya Alyssa Azzahra - 2506599270 - My Closet
Faiz Yusuf Elriki - 2506607921 - Chat
Naila Husna Teguh Suasono - 2506620444 - Swap / Barter

# daftar modul
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

# public / mock api
TODO

# jenis / peran pengguna
1. Guest (Belum Login)
   Hak akses: Hanya baca (read-only) pada konten publik.
   Bisa: Menjelajahi feed outfit inspirasi, melihat katalog pakaian publik di closet orang lain, menggunakan fitur pencarian/filter.
   Tidak bisa: Mengunggah outfit, menambah pakaian ke closet, mengakses chat, mengajukan barter, memberikan ulasan.

2. Registered User (Sudah Login)
   Hak akses: Semua hak Guest, ditambah kemampuan berinteraksi penuh.
   Bisa: Upload outfit ke feed, menambah pakaian ke My Closet, chat dengan user lain, mengajukan swap/barter.

3. Verified User (Sudah Terverifikasi)
   Hak akses: Semua hak Registered User, ditambah badge verified.
   Bisa: Menampilkan badge verified di profil dan feed, **TODO: tentukan apakah ada pembatasan tambahan (mis. hanya user verified yang bisa barter dengan user verified lain), dan tentukan syarat verifikasi (email confirmed, KTP, jumlah barter sukses, dll).**
