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
  const queueHeader = document.querySelector(".cockpit-header, .queue-header");
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
    const key = event.key.toLowerCase();
    if (key === "a") {
      event.preventDefault();
      submitWith({ advance: "next", statusOverride: "approved" });
      return;
    }
    if (key === "r") {
      event.preventDefault();
      submitWith({ advance: "next", statusOverride: "rejected" });
      return;
    }
    if (key === "s") {
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

function bindGenerateForms() {
  document.querySelectorAll(".js-generate-form").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector(".js-generate-button");
      if (!button) return;
      button.disabled = true;
      button.textContent = button.dataset.loadingText || "Working...";
    });
  });
}

function bindFilePickerSummaries() {
  document.querySelectorAll(".js-file-input").forEach((input) => {
    input.addEventListener("change", () => {
      const target = input.dataset.summaryTarget ? document.querySelector(input.dataset.summaryTarget) : null;
      if (!target) return;
      const count = input.files ? input.files.length : 0;
      if (!count) {
        target.textContent = "No files selected";
        return;
      }
      if (count === 1) {
        target.textContent = input.files[0].webkitRelativePath || input.files[0].name;
        return;
      }
      target.textContent = `${count} files selected`;
    });
  });
}

function bindFolderDialogs() {
  document.querySelectorAll(".js-folder-dialog").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = button.dataset.target ? document.querySelector(button.dataset.target) : null;
      if (!target || !button.dataset.dialogUrl) return;
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = "Browsing...";
      try {
        const response = await fetch(button.dataset.dialogUrl, { headers: { Accept: "application/json" } });
        const payload = await response.json();
        if (!response.ok || payload.error) {
          throw new Error(payload.error || "Folder dialog failed");
        }
        if (payload.path) {
          target.value = payload.path;
          target.dispatchEvent(new Event("change", { bubbles: true }));
        }
      } catch (error) {
        window.alert(error.message || "Folder dialog failed");
      } finally {
        button.disabled = false;
        button.textContent = originalText;
      }
    });
  });
}

function bindPanZoomViewers() {
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  document.querySelectorAll(".js-panzoom-pane").forEach((pane) => {
    const target = pane.querySelector(".js-panzoom-target");
    if (!target) return;
    target.querySelectorAll("img").forEach((image) => {
      image.draggable = false;
      image.addEventListener("dragstart", (event) => event.preventDefault());
    });

    const state = {
      scale: 1,
      x: 0,
      y: 0,
      dragging: false,
      moved: false,
      startClientX: 0,
      startClientY: 0,
      startX: 0,
      startY: 0,
    };

    const baseTransform = target.dataset.baseTransform || "";
    target.dataset.baseTransform = baseTransform;

    const panBounds = () => {
      const paneRect = pane.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const unscaledWidth = targetRect.width / state.scale;
      const unscaledHeight = targetRect.height / state.scale;
      const scaledWidth = unscaledWidth * state.scale;
      const scaledHeight = unscaledHeight * state.scale;
      const overflowX = Math.max(0, (scaledWidth - paneRect.width) / 2);
      const overflowY = Math.max(0, (scaledHeight - paneRect.height) / 2);
      return {
        x: overflowX + paneRect.width * 0.35,
        y: overflowY + paneRect.height * 0.35,
      };
    };

    const clampPan = () => {
      if (state.scale <= 1.01) {
        state.x = 0;
        state.y = 0;
        return;
      }
      const bounds = panBounds();
      state.x = clamp(state.x, -bounds.x, bounds.x);
      state.y = clamp(state.y, -bounds.y, bounds.y);
    };

    const render = () => {
      clampPan();
      target.style.transform = `${baseTransform} translate3d(${state.x}px, ${state.y}px, 0) scale(${state.scale})`;
      pane.classList.toggle("is-zoomed", state.scale > 1.01);
      pane.classList.toggle("is-panning", state.dragging);
    };

    const reset = () => {
      state.scale = 1;
      state.x = 0;
      state.y = 0;
      state.dragging = false;
      state.moved = false;
      render();
    };

    pane.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        const oldScale = state.scale;
        const zoomFactor = Math.exp(-event.deltaY * 0.001);
        const nextScale = clamp(oldScale * zoomFactor, 1, 6);
        if (nextScale === oldScale) return;

        const paneRect = pane.getBoundingClientRect();
        const pointerX = event.clientX - (paneRect.left + paneRect.width / 2);
        const pointerY = event.clientY - (paneRect.top + paneRect.height / 2);
        const ratio = nextScale / oldScale;
        state.x = pointerX - (pointerX - state.x) * ratio;
        state.y = pointerY - (pointerY - state.y) * ratio;
        state.scale = nextScale;

        if (state.scale <= 1.01) {
          state.scale = 1;
          state.x = 0;
          state.y = 0;
        }
        render();
      },
      { passive: false }
    );

    pane.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || state.scale <= 1.01) return;
      event.preventDefault();
      state.dragging = true;
      state.moved = false;
      state.startClientX = event.clientX;
      state.startClientY = event.clientY;
      state.startX = state.x;
      state.startY = state.y;
      pane.setPointerCapture(event.pointerId);
      render();
    });

    pane.addEventListener("pointermove", (event) => {
      if (!state.dragging) return;
      event.preventDefault();
      const dx = event.clientX - state.startClientX;
      const dy = event.clientY - state.startClientY;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) state.moved = true;
      state.x = state.startX + dx;
      state.y = state.startY + dy;
      render();
    });

    const endDrag = (event) => {
      if (!state.dragging) return;
      state.dragging = false;
      if (pane.hasPointerCapture(event.pointerId)) {
        pane.releasePointerCapture(event.pointerId);
      }
      render();
    };

    pane.addEventListener("pointerup", endDrag);
    pane.addEventListener("pointercancel", endDrag);
    pane.addEventListener("dblclick", reset);
    pane.addEventListener(
      "click",
      (event) => {
        if (!state.moved) return;
        state.moved = false;
        event.preventDefault();
        event.stopImmediatePropagation();
      },
      true
    );
  });
}

document.addEventListener("DOMContentLoaded", () => {
  applyBoundingBoxes();
  bindQueueSelection();
  bindReviewShortcuts();
  bindGenerateForms();
  bindFilePickerSummaries();
  bindFolderDialogs();
  bindPanZoomViewers();
});
