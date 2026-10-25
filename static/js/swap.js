
document.addEventListener("DOMContentLoaded", function () {
    // Ambil elemen dari swap.html
    const cards = Array.from(document.querySelectorAll(".swap-card"));
    const finished = document.getElementById("swap-finished");
    const feedback = document.getElementById("swap-feedback");
    const modal = document.getElementById("swap-modal");
    const closeButton = document.getElementById("close-details");

    let currentIndex = 0;
    let isAnimating = false;

    // Menampilkan kartu yang sedang aktif
    function showCards() {
        cards.forEach((card, index) => {
            const position = index - currentIndex;

            card.hidden = position < 0 || position > 1;

            if (position >= 0 && position <= 1) {
                card.style.zIndex = String(10 - position);
                card.style.opacity = "1";
                card.style.transform =
                    `translateY(${position * 8}px) scale(${1 - position * 0.04})`;
                card.style.pointerEvents =
                    position === 0 ? "auto" : "none";
            }
        });

        finished.hidden = currentIndex < cards.length;
    }

    // Fungsi swipe kiri atau kanan
    function swipe(direction) {
        if (isAnimating || currentIndex >= cards.length) {
            return;
        }

        isAnimating = true;

        const activeCard = cards[currentIndex];
        const itemName = activeCard.dataset.name;

        activeCard.classList.remove("is-dragging");

        if (direction === "left") {
            activeCard.style.transform =
                "translateX(-120vw) rotate(-20deg)";
            feedback.textContent = `Skipped ${itemName}`;
        } else {
            activeCard.style.transform =
                "translateX(120vw) rotate(20deg)";
            feedback.textContent =
                `Interested in ${itemName}!`;
        }

        activeCard.style.opacity = "0";

        // Tunggu animasi selesai
        setTimeout(() => {
            currentIndex++;
            isAnimating = false;
            showCards();
        }, 280);
    }

    // Mengaktifkan tombol pada setiap kartu
    cards.forEach(card => {

        const rejectButton = card.querySelector(".swap-reject");
        const acceptButton = card.querySelector(".swap-accept");
        const detailButton = card.querySelector(".swap-details");

        // Tombol X
        rejectButton.addEventListener("click", () => {
            if (card === cards[currentIndex]) {
                swipe("left");
            }
        });

        // Tombol centang
        acceptButton.addEventListener("click", () => {
            if (card === cards[currentIndex]) {
                swipe("right");
            }
        });

        // Tombol View Details
        detailButton.addEventListener("click", () => {
            document.getElementById("detail-name").textContent =
                card.dataset.name;

            document.getElementById("detail-description").textContent =
                card.dataset.description;

            document.getElementById("detail-size").textContent =
                "Size: " + card.dataset.size;

            document.getElementById("detail-condition").textContent =
                "Condition: " + card.dataset.condition;

            document.getElementById("detail-owner").textContent =
                "Owner: " + card.dataset.owner;

            modal.showModal();
        });

        // Swipe menggunakan mouse atau touch
        let startX = null;

        card.addEventListener("pointerdown", event => {
            if (card !== cards[currentIndex] || isAnimating) return;
            if (event.target.closest("button")) return;
            if (event.pointerType === "mouse" && event.button !== 0) return;

            startX = event.clientX;

            card.setPointerCapture(event.pointerId);
            card.classList.add("is-dragging");
        });

        card.addEventListener("pointermove", event => {
            if (startX === null) return;

            const distance = event.clientX - startX;

            card.style.transform =
                `translateX(${distance}px) rotate(${distance / 20}deg)`;
        });

        card.addEventListener("pointerup", event => {
            if (startX === null) return;

            const distance = event.clientX - startX;
            startX = null;

            card.classList.remove("is-dragging");

            if (distance > 90) {
                swipe("right");
            } else if (distance < -90) {
                swipe("left");
            } else {
                showCards();
            }
        });

        card.addEventListener("pointercancel", () => {
            startX = null;
            card.classList.remove("is-dragging");
            showCards();
        });
    });

    // Menutup modal detail pakaian
    closeButton.addEventListener("click", () => {
        modal.close();
    });

    // Menampilkan kartu pertama
    showCards();
});