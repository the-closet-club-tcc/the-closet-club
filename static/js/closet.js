document.addEventListener("DOMContentLoaded", function () {
    // Ubah status ketersediaan langsung saat dropdown di kartu diganti
    document.querySelectorAll("select[data-autosubmit]").forEach(select => {
        select.addEventListener("change", () => select.form.submit());
    });

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
});
