function applyBoundingBoxes() {
  document.querySelectorAll(".js-image-stage").forEach((stage) => {
    const image = stage.querySelector("img");
    if (!image) return;
    const draw = () => {
      const scaleX = image.clientWidth / image.naturalWidth;
      const scaleY = image.clientHeight / image.naturalHeight;
      stage.querySelectorAll(".bbox").forEach((box) => {
        box.style.left = `${Number(box.dataset.x) * scaleX}px`;
        box.style.top = `${Number(box.dataset.y) * scaleY}px`;
        box.style.width = `${Number(box.dataset.w) * scaleX}px`;
        box.style.height = `${Number(box.dataset.h) * scaleY}px`;
      });
    };
    if (image.complete) {
      draw();
    } else {
      image.addEventListener("load", draw);
    }
    window.addEventListener("resize", draw);
  });
}

async function bindVerifyButtons() {
  document.querySelectorAll(".js-verify-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const outputId = button.dataset.output;
      const output = document.getElementById(outputId);
      output.textContent = "Running verification...";
      try {
        const response = await fetch(button.dataset.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        const payload = await response.json();
        if (!response.ok) {
          output.textContent = payload.error || "Verification failed.";
          return;
        }
        const result = payload.verification;
        output.innerHTML = `
          <div><strong>Verdict:</strong> ${result.verdict || "n/a"}</div>
          <div><strong>Confidence:</strong> ${result.confidence ?? "n/a"}</div>
          <div><strong>Suggestion:</strong> ${result.corrected_text || "n/a"}</div>
          <div><strong>Reasoning:</strong> ${result.reasoning || "n/a"}</div>
        `;
      } catch (error) {
        output.textContent = error.message;
      }
    });
  });
}

function bindQueueSelection() {
  document.querySelectorAll(".js-master-checkbox").forEach((master) => {
    master.addEventListener("change", () => {
      document.querySelectorAll(master.dataset.target).forEach((checkbox) => {
        checkbox.checked = master.checked;
      });
    });
  });

  document.querySelectorAll(".js-toggle-checkboxes").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(button.dataset.target).forEach((checkbox) => {
        checkbox.checked = !checkbox.checked;
      });
    });
  });
}

function bindReviewShortcuts() {
  const reviewForm = document.querySelector(".js-review-form");
  const queueHeader = document.querySelector(".queue-header");
  if (!reviewForm || !queueHeader) return;

  const submitWith = ({ advance = "", statusOverride = "" } = {}) => {
    const advanceInput = reviewForm.querySelector('input[name="advance"]');
    if (advanceInput) advanceInput.value = advance;
    let existingOverride = reviewForm.querySelector('input[name="status_override"]');
    if (!existingOverride) {
      existingOverride = document.createElement("input");
      existingOverride.type = "hidden";
      existingOverride.name = "status_override";
      reviewForm.appendChild(existingOverride);
    }
    existingOverride.value = statusOverride;
    reviewForm.requestSubmit();
  };

  document.addEventListener("keydown", (event) => {
    const tagName = document.activeElement?.tagName || "";
    if (tagName === "TEXTAREA" || tagName === "INPUT" || tagName === "SELECT") {
      return;
    }
    if (event.key === "a") {
      event.preventDefault();
      submitWith({ advance: "next", statusOverride: "approved" });
      return;
    }
    if (event.key === "r") {
      event.preventDefault();
      submitWith({ advance: "next", statusOverride: "rejected" });
      return;
    }
    if (event.key === "s") {
      event.preventDefault();
      submitWith();
      return;
    }
    if (event.key === "[" && queueHeader.dataset.prevUrl) {
      event.preventDefault();
      window.location.href = queueHeader.dataset.prevUrl;
      return;
    }
    if (event.key === "]" && queueHeader.dataset.nextUrl) {
      event.preventDefault();
      window.location.href = queueHeader.dataset.nextUrl;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  applyBoundingBoxes();
  bindVerifyButtons();
  bindQueueSelection();
  bindReviewShortcuts();
});
