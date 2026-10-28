
document.addEventListener("DOMContentLoaded", function () {
    // Ambil elemen dari swap.html
    const cards = Array.from(document.querySelectorAll(".swap-card"));
    const finished = document.getElementById("swap-finished");
    const finishedMessage = document.getElementById("swap-finished-message");
    const reviewButton = document.getElementById("review-skipped");
    const feedback = document.getElementById("swap-feedback");
    const modal = document.getElementById("swap-modal");
    const closeButton = document.getElementById("close-details");
    const deck = document.getElementById("swap-deck");

    document.querySelectorAll(".swap-details").forEach(button => {
        button.addEventListener("click", () => {
            const card = button.closest("[data-name]");
            document.getElementById("detail-name").textContent = card.dataset.name;
            document.getElementById("detail-description").textContent = card.dataset.description;
            document.getElementById("detail-size").textContent = card.dataset.size;
            document.getElementById("detail-condition").textContent = card.dataset.condition;
            document.getElementById("detail-offer").textContent = card.dataset.offer;
            document.getElementById("detail-owner").textContent = card.dataset.owner;
            modal.showModal();
        });
    });

    closeButton.addEventListener("click", () => {
        modal.close();
    });

    if (!deck) return;

    let currentIndex = 0;
    let isAnimating = false;
    let activeCards = cards.slice();
    let skippedCards = [];

    // Menampilkan kartu yang sedang aktif
    function showCards() {
        cards.forEach(card => {
            const position = activeCards.indexOf(card) - currentIndex;

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

        finished.hidden = currentIndex < activeCards.length;
        reviewButton.hidden = skippedCards.length === 0;
        if (cards.length > 0) {
            finishedMessage.textContent = skippedCards.length > 0
                ? "Want another look? Revisit the pieces you skipped."
                : "Revisit your saved pieces in Interested items.";
        }
    }

    // Fungsi swipe kiri atau kanan
    async function swipe(direction) {
        if (isAnimating || currentIndex >= activeCards.length) {
            return;
        }

        isAnimating = true;

        const activeCard = activeCards[currentIndex];
        const itemName = activeCard.dataset.name;

        activeCard.classList.remove("is-dragging");

        if (direction === "right") {
            if (deck.dataset.authenticated !== "true") {
                window.location.assign(deck.dataset.loginUrl);
                return;
            }

            feedback.textContent = "Sending your swap request...";
            activeCard.setAttribute("aria-busy", "true");
            let failureMessage = "Couldn't send this request. Please try again.";
            try {
                const response = await fetch(activeCard.dataset.saveUrl, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-CSRFToken": document.querySelector('[name="csrfmiddlewaretoken"]').value,
                        "Accept": "application/json",
                    },
                });
                if (response.status === 401) {
                    window.location.assign(deck.dataset.loginUrl);
                    isAnimating = false;
                    showCards();
                    return;
                }
                const result = await response.json();
                if (!response.ok || result.saved !== true) {
                    failureMessage = result.error || failureMessage;
                    throw new Error(failureMessage);
                }
            } catch {
                isAnimating = false;
                showCards();
                feedback.textContent = failureMessage;
                return;
            } finally {
                activeCard.removeAttribute("aria-busy");
            }
        }

        if (direction === "left") {
            skippedCards.push(activeCard);
            activeCard.style.transform =
                "translateX(-120vw) rotate(-20deg)";
            feedback.textContent = `Skipped ${itemName}`;
        } else {
            activeCard.style.transform =
                "translateX(120vw) rotate(20deg)";
            feedback.textContent =
                `Swap request for ${itemName} is in Outgoing requests. The piece is also saved to Interested items.`;
        }

        activeCard.style.opacity = "0";

        // Tunggu animasi selesai
        setTimeout(() => {
            currentIndex++;
            isAnimating = false;
            showCards();
        }, 280);
    }

    reviewButton.addEventListener("click", () => {
        if (isAnimating || finished.hidden || skippedCards.length === 0) return;

        activeCards = skippedCards.slice();
        skippedCards = [];
        currentIndex = 0;
        feedback.textContent = "Take another look at the pieces you skipped.";
        showCards();
        activeCards[0].querySelector(".swap-details").focus({ preventScroll: true });
    });

    // Mengaktifkan tombol pada setiap kartu
    cards.forEach(card => {

        const rejectButton = card.querySelector(".swap-reject");
        const acceptButton = card.querySelector(".swap-accept");

        // Tombol X
        rejectButton.addEventListener("click", () => {
            if (card === activeCards[currentIndex]) {
                swipe("left");
            }
        });

        // Tombol centang
        acceptButton.addEventListener("click", () => {
            if (card === activeCards[currentIndex]) {
                swipe("right");
            }
        });

        // Swipe menggunakan mouse atau touch
        let startX = null;

        card.addEventListener("pointerdown", event => {
            if (card !== activeCards[currentIndex] || isAnimating) return;
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

    // Menampilkan kartu pertama
    showCards();
});
