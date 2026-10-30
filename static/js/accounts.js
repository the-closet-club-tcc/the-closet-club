(() => {
    const setFeedback = (element, message, isError = false) => {
        if (!element) return;
        element.textContent = message;
        element.classList.toggle("is-error", isError);
    };

    const submitAsync = async (form) => {
        const response = await fetch(form.action, {
            method: "POST",
            body: new FormData(form),
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "Something went wrong. Please try again.");
        }
        return result;
    };

    document.querySelectorAll(".async-verification-form").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const button = form.querySelector("button[type='submit']");
            const feedback = document.getElementById("verification-feedback");
            button.disabled = true;
            try {
                const result = await submitAsync(form);
                if (result.status === "pending" || result.status === "verified") {
                    feedback.replaceChildren();
                    const guidance = document.getElementById("verification-guidance");
                    if (guidance) guidance.remove();
                    form.remove();
                    const status = document.createElement("p");
                    status.className = result.status === "verified" ? "verification-success" : "verification-pending";
                    status.textContent = result.status === "verified"
                        ? "✓ Your account is verified."
                        : "Your verification request is pending review.";
                    document.getElementById("profile-verification").append(status);
                } else {
                    setFeedback(feedback, result.message);
                }
            } catch (error) {
                setFeedback(feedback, error.message, true);
            } finally {
                if (button.isConnected) button.disabled = false;
            }
        });
    });

    document.querySelectorAll(".async-review-form").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const button = form.querySelector("button[type='submit']");
            const feedback = document.getElementById("review-feedback");
            button.disabled = true;
            try {
                const result = await submitAsync(form);
                setFeedback(feedback, result.message);

                const emptyMessage = document.getElementById("empty-review-message");
                if (emptyMessage) emptyMessage.remove();

                const card = document.createElement("article");
                card.className = "profile-review-card";
                const header = document.createElement("div");
                header.className = "profile-review-header";
                const username = document.createElement("strong");
                username.textContent = result.review.username;
                const rating = document.createElement("span");
                rating.className = "review-display-rating";
                rating.textContent = `★ ${result.review.rating} / 5`;
                header.append(username, rating);
                const comment = document.createElement("p");
                comment.textContent = result.review.comment;
                const date = document.createElement("small");
                date.textContent = result.review.date;
                card.append(header, comment, date);
                document.getElementById("review-list").append(card);

                const summary = document.getElementById("profile-rating-summary");
                if (summary) summary.textContent = `★ ${result.review.average} / 5 (${result.review.count} reviews)`;
                form.remove();
            } catch (error) {
                setFeedback(feedback, error.message, true);
                button.disabled = false;
            }
        });
    });
})();
