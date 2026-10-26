// Ubah status ketersediaan langsung saat dropdown di kartu diganti.
// Pakai event delegation supaya tetap jalan setelah isi grid diganti oleh live search.
document.addEventListener("change", function (event) {
    if (event.target.matches("select[data-autosubmit]")) {
        event.target.form.submit();
    }
});

document.addEventListener("DOMContentLoaded", function () {
    // Preview foto sebelum diunggah (form tambah/edit)
    const fileInput = document.querySelector(".closet-form-photo input[type='file']");
    const previewImg = document.getElementById("photo-preview-img");
    const previewEmpty = document.getElementById("photo-preview-empty");

    if (fileInput && previewImg) {
        let objectUrl = null;

        fileInput.addEventListener("change", () => {
            const file = fileInput.files[0];
            if (!file || !file.type.startsWith("image/")) return;

            if (objectUrl) URL.revokeObjectURL(objectUrl);
            objectUrl = URL.createObjectURL(file);

            previewImg.src = objectUrl;
            previewImg.hidden = false;
            if (previewEmpty) previewEmpty.hidden = true;
        });
    }

    // Live search: debounce + ganti isi hasil tanpa reload halaman
    const filterForm = document.querySelector(".closet-filters");
    const results = document.getElementById("closet-results");

    if (filterForm && results) {
        let timer = null;
        let controller = null;

        async function refreshResults() {
            // Kumpulkan parameter, lewati yang kosong supaya URL tetap bersih
            const params = new URLSearchParams();
            new FormData(filterForm).forEach((value, key) => {
                if (value) params.append(key, value);
            });
            const query = params.toString();
            const url = query ? `${location.pathname}?${query}` : location.pathname;

            // Batalkan request sebelumnya yang belum selesai
            if (controller) controller.abort();
            controller = new AbortController();

            try {
                const response = await fetch(url, { signal: controller.signal });
                const doc = new DOMParser().parseFromString(await response.text(), "text/html");
                const fresh = doc.getElementById("closet-results");

                if (!response.ok || !fresh) {
                    filterForm.submit();   // fallback ke cara biasa
                    return;
                }

                results.innerHTML = fresh.innerHTML;
                history.replaceState(null, "", url);
            } catch (error) {
                if (error.name !== "AbortError") filterForm.submit();
            }
        }

        // Tunggu 400 ms setelah user berhenti mengetik / mengganti dropdown
        filterForm.addEventListener("input", () => {
            clearTimeout(timer);
            timer = setTimeout(refreshResults, 400);
        });

        // Enter / tombol Filter tetap jalan lewat refreshResults, tanpa reload
        filterForm.addEventListener("submit", event => {
            event.preventDefault();
            clearTimeout(timer);
            refreshResults();
        });
    }
});