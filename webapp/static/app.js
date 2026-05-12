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

function bindBulkReviewForms() {
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
  const statusPanel = document.querySelector("[data-bulk-review-status]");
  const statusUrl = statusPanel?.dataset.statusUrl || "";
  let pollTimer = null;

  const parsePayload = async (response) => {
    const text = await response.text();
    try {
      return text ? JSON.parse(text) : {};
    } catch {
      return { error: text || response.statusText };
    }
  };

  const setStatusText = (selector, value) => {
    const node = statusPanel?.querySelector(selector);
    if (node) node.textContent = value;
  };

  const renderStatus = (payload) => {
    if (!statusPanel || !payload) return;
    statusPanel.hidden = false;
    const state = payload.state || "unknown";
    const selected = Number(payload.total_selected || 0);
    const eligible = Number(payload.eligible_count || 0);
    const updated = Number(payload.updated_count || 0);
    const skipped = Number(payload.skipped_count || 0);
    const action = payload.requested_status === "approved" ? "Accepting" : payload.requested_status === "rejected" ? "Rejecting" : "Updating";
    statusPanel.dataset.jobId = payload.id || statusPanel.dataset.jobId || "";
    setStatusText("[data-bulk-review-state]", state.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()));
    if (state === "done") {
      setStatusText("[data-bulk-review-message]", `Bulk review complete.`);
    } else if (state === "failed") {
      setStatusText("[data-bulk-review-message]", payload.error || "Bulk review failed.");
    } else {
      setStatusText("[data-bulk-review-message]", `${action} selected review items.`);
    }
    setStatusText("[data-bulk-review-detail]", `${updated} updated, ${skipped} skipped, ${eligible || selected} eligible.`);
  };

  const setBulkButtonsDisabled = (disabled) => {
    document.querySelectorAll(".js-bulk-review-form button[type='submit']").forEach((button) => {
      button.disabled = disabled;
    });
  };

  const pollStatus = async ({ reloadWhenDone = false } = {}) => {
    if (!statusUrl || !statusPanel?.dataset.jobId) return null;
    const url = `${statusUrl}?job_id=${encodeURIComponent(statusPanel.dataset.jobId)}`;
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    const payload = await parsePayload(response);
    if (!response.ok) throw new Error(payload.error || "Bulk review status is unavailable.");
    renderStatus(payload);
    if (payload.state === "done") {
      window.clearInterval(pollTimer);
      pollTimer = null;
      if (reloadWhenDone) window.location.reload();
    }
    if (payload.state === "failed") {
      window.clearInterval(pollTimer);
      pollTimer = null;
      setBulkButtonsDisabled(false);
    }
    return payload;
  };

  const startPolling = ({ reloadWhenDone = false } = {}) => {
    if (pollTimer || !statusUrl || !statusPanel?.dataset.jobId) return;
    setBulkButtonsDisabled(true);
    pollStatus({ reloadWhenDone }).catch(() => {});
    pollTimer = window.setInterval(() => {
      pollStatus({ reloadWhenDone }).catch(() => {});
    }, 2500);
  };

  if (statusPanel?.dataset.jobId) {
    startPolling({ reloadWhenDone: true });
  }

  document.querySelectorAll(".js-bulk-review-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitter = event.submitter;
      const formData = new FormData(form);
      if (submitter?.name) formData.set(submitter.name, submitter.value);
      if (!formData.get("csrf_token")) formData.set("csrf_token", csrfToken());
      setBulkButtonsDisabled(true);
      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: { Accept: "application/json" },
          body: formData,
        });
        const payload = await parsePayload(response);
        if (response.status === 409 && payload.job?.id) {
          statusPanel.dataset.jobId = payload.job.id;
          renderStatus(payload.job);
          startPolling({ reloadWhenDone: true });
          return;
        }
        if (!response.ok || payload.error) {
          throw new Error(payload.error || "Bulk review could not start.");
        }
        if (payload.job_id) {
          statusPanel.dataset.jobId = payload.job_id;
          renderStatus({ id: payload.job_id, state: payload.state || "queued" });
          startPolling({ reloadWhenDone: true });
        }
      } catch (error) {
        if (statusPanel) {
          statusPanel.hidden = false;
          setStatusText("[data-bulk-review-message]", error.message || "Bulk review could not start.");
          setStatusText("[data-bulk-review-detail]", "");
          setStatusText("[data-bulk-review-state]", "Failed");
        }
        setBulkButtonsDisabled(false);
      }
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
    if (document.querySelector(".js-crop-adjust-wrap.is-adjusting, .js-crop-adjust-wrap.is-geometry-correcting")) {
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
    if (form.classList.contains("js-chunked-upload-form")) return;
    if (form.classList.contains("js-populate-form")) return;
    form.addEventListener("submit", () => {
      const button = form.querySelector(".js-generate-button");
      if (!button) return;
      button.disabled = true;
      button.textContent = button.dataset.loadingText || "Working...";
    });
  });
}

function bindProjectDeleteDialog() {
  const dialog = document.querySelector("[data-project-delete-dialog]");
  if (!dialog) return;
  const form = dialog.querySelector("form");
  const input = dialog.querySelector("[data-project-delete-input]");
  const submit = dialog.querySelector("[data-project-delete-submit]");
  const name = dialog.querySelector("[data-project-delete-name]");
  const cancel = dialog.querySelector("[data-project-delete-cancel]");
  if (!form || !input || !submit) return;

  const closeDialog = () => {
    if (typeof dialog.close === "function") {
      dialog.close();
    }
  };

  document.querySelectorAll("[data-project-delete-open]").forEach((button) => {
    button.addEventListener("click", () => {
      form.action = button.dataset.deleteUrl || "";
      if (name) name.textContent = button.dataset.projectName || "this project";
      input.value = "";
      submit.disabled = true;
      if (typeof dialog.showModal === "function") {
        dialog.showModal();
      }
      input.focus();
    });
  });

  input.addEventListener("input", () => {
    submit.disabled = input.value !== "DELETE";
  });
  if (cancel) {
    cancel.addEventListener("click", closeDialog);
  }
}

function bindPopulateWorkspace() {
  const statusPanel = document.querySelector("[data-populate-status-url]");
  const statusUrl = statusPanel?.dataset.populateStatusUrl || document.querySelector(".js-populate-form")?.dataset.statusUrl;
  let pollTimer = null;

  const titleCase = (value) =>
    String(value || "n/a")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());

  const setText = (selector, value) => {
    const node = document.querySelector(selector);
    if (node) node.textContent = value;
  };

  const setField = (name, value) => {
    const node = document.querySelector(`[data-populate-field="${name}"]`);
    if (node) node.textContent = value ?? 0;
  };

  const renderStatus = (payload) => {
    if (!statusPanel || !payload) return;
    const state = payload.state || "idle";
    statusPanel.className = `populate-status populate-status-${state}`;
    setText("[data-populate-message]", payload.message || "Workspace population has not run yet.");
    setText("[data-populate-state]", titleCase(state));
    setField("stage", titleCase(payload.stage || "n/a"));
    setField("package_count", payload.package_count || 0);
    setField("document_count", payload.document_count || 0);
    setField("sheet_count", payload.sheet_count || 0);
    setField("cloud_count", payload.cloud_count || 0);
    setField("change_item_count", payload.change_item_count || 0);
    setField("cache_hits", payload.cache_hits || 0);
    setField("pre_review_total_count", payload.pre_review_total_count || 0);
    setField("pre_review_2_count", payload.pre_review_2_count || 0);
    setField("pre_review_failed_count", payload.pre_review_failed_count || 0);
    setField("pre_review_cache_hits", payload.pre_review_cache_hits || 0);
    setField("staged_pdf_count", payload.staged_pdf_count || 0);
    setField("live_artifact_count", payload.live_artifact_count || 0);

    const progress = document.querySelector("[data-populate-progress-wrap]");
    if (progress) progress.hidden = state !== "running";

    const detail = document.querySelector("[data-populate-detail]");
    if (detail) {
      const parts = [];
      if (payload.staged_pdf_count) parts.push(`${payload.staged_pdf_count} staged PDF${payload.staged_pdf_count === 1 ? "" : "s"}`);
      if (payload.live_artifact_count) parts.push(`${payload.live_artifact_count} live artifact${payload.live_artifact_count === 1 ? "" : "s"} written`);
      if (payload.inferred_cloudhammer_page_count) parts.push(`${payload.inferred_cloudhammer_page_count} cataloged page rows`);
      if (payload.inferred_cloudhammer_candidate_count) parts.push(`${payload.inferred_cloudhammer_candidate_count} candidate rows`);
      if (payload.pre_review_total_count) parts.push(`Pre Review ${payload.pre_review_2_count || 0} of ${payload.pre_review_total_count}`);
      detail.textContent = parts.join(" | ");
    }

    const error = document.querySelector("[data-populate-error]");
    if (error) {
      error.hidden = !payload.error;
      error.textContent = payload.error || "";
    }
  };

  const pollStatus = async ({ reloadWhenFinished = false } = {}) => {
    if (!statusUrl) return null;
    const response = await fetch(statusUrl, { headers: { Accept: "application/json" } });
    if (!response.ok) return null;
    const payload = await response.json();
    renderStatus(payload);
    if (reloadWhenFinished && (payload.state === "done" || payload.state === "failed")) {
      window.location.reload();
    }
    return payload;
  };

  const startPolling = ({ reloadWhenFinished = false } = {}) => {
    if (pollTimer || !statusUrl) return;
    pollStatus({ reloadWhenFinished }).catch(() => {});
    pollTimer = window.setInterval(() => {
      pollStatus({ reloadWhenFinished }).catch(() => {});
    }, 3000);
  };

  if (statusPanel && statusUrl) {
    const state = document.querySelector("[data-populate-state]")?.textContent?.trim().toLowerCase();
    if (state === "running") startPolling({ reloadWhenFinished: true });
  }

  document.querySelectorAll(".js-populate-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector(".js-generate-button");
      const originalButtonText = button ? button.textContent : "";
      if (button) {
        button.disabled = true;
        button.textContent = button.dataset.loadingText || "Populating...";
      }
      renderStatus({
        state: "running",
        stage: "request_started",
        message: "Populate request sent. Keeping this page updated while drawing analysis runs.",
      });
      startPolling({ reloadWhenFinished: true });
      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { Accept: "text/html" },
        });
        if (!response.ok) throw new Error("Populate failed to start.");
        window.location.reload();
      } catch (error) {
        renderStatus({
          state: "failed",
          stage: "request_failed",
          message: error.message || "Populate request failed.",
          error: error.message || "Populate request failed.",
        });
        if (button) {
          button.disabled = false;
          button.textContent = originalButtonText;
        }
      }
    });
  });
}

function bindChunkedUploadForms() {
  const fileEntriesForForm = (form) => {
    const entries = [];
    form.querySelectorAll('input[type="file"]').forEach((input) => {
      Array.from(input.files || []).forEach((file) => {
        entries.push({
          file,
          relativePath: file.webkitRelativePath || file.name,
        });
      });
    });
    return entries;
  };

  const setUploadStatus = (form, { text = "", count = "", percent = 0, hidden = false } = {}) => {
    const status = form.querySelector("[data-upload-status]");
    if (!status) return;
    status.hidden = hidden;
    const textNode = status.querySelector("[data-upload-status-text]");
    const countNode = status.querySelector("[data-upload-status-count]");
    const progressNode = status.querySelector("[data-upload-progress]");
    if (textNode && text) textNode.textContent = text;
    if (countNode) countNode.textContent = count;
    if (progressNode) progressNode.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  };

  const responsePayload = async (response) => {
    const text = await response.text();
    try {
      return text ? JSON.parse(text) : {};
    } catch {
      return { error: text || response.statusText };
    }
  };

  const csrfTokenForForm = (form) => {
    const input = form.querySelector('input[name="csrf_token"]');
    if (input && input.value) return input.value;
    return document.querySelector('meta[name="csrf-token"]')?.content || "";
  };

  const abortUpload = async (form, uploadId, { beacon = false } = {}) => {
    if (!uploadId || !form.dataset.abortUrl) return;
    const payload = JSON.stringify({ upload_id: uploadId, csrf_token: csrfTokenForForm(form) });
    if (beacon && navigator.sendBeacon) {
      const body = new Blob([payload], { type: "application/json" });
      navigator.sendBeacon(form.dataset.abortUrl, body);
      return;
    }
    try {
      await fetch(form.dataset.abortUrl, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: payload,
        keepalive: beacon,
      });
    } catch {
      // Stale server-side upload folders are also cleaned opportunistically.
    }
  };

  document.querySelectorAll(".js-chunked-upload-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      const entries = fileEntriesForForm(form);
      if (!entries.length) return;

      event.preventDefault();
      const button = form.querySelector(".js-generate-button");
      const originalButtonText = button ? button.textContent : "";
      if (button) {
        button.disabled = true;
        button.textContent = button.dataset.loadingText || "Uploading...";
      }
      setUploadStatus(form, { text: "Preparing upload...", count: "", percent: 0, hidden: false });

      let uploadId = "";
      let completed = false;
      const abortOnUnload = () => {
        if (!completed && uploadId) abortUpload(form, uploadId, { beacon: true });
      };
      window.addEventListener("beforeunload", abortOnUnload);

      try {
        const formData = new FormData(form);
        const initResponse = await fetch(form.dataset.initUrl, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            purpose: form.dataset.uploadPurpose,
            package_label: formData.get("package_label") || "",
            revision_number: formData.get("revision_number") || "",
            revision_set_id: formData.get("revision_set_id") || "",
            csrf_token: csrfTokenForForm(form),
            files: entries.map(({ file, relativePath }) => ({
              name: file.name,
              relative_path: relativePath,
              size: file.size,
            })),
          }),
        });
        const initPayload = await responsePayload(initResponse);
        if (!initResponse.ok || initPayload.error) {
          throw new Error(initPayload.error || "Upload could not start.");
        }

        uploadId = initPayload.upload_id;
        const chunkSize = Number(initPayload.chunk_size || 8 * 1024 * 1024);
        const totalBytes = entries.reduce((sum, entry) => sum + entry.file.size, 0);
        let uploadedBytes = 0;
        let uploadedChunks = 0;
        const totalChunks = entries.reduce((sum, entry) => sum + Math.ceil(entry.file.size / chunkSize), 0);

        for (let fileIndex = 0; fileIndex < entries.length; fileIndex += 1) {
          const { file, relativePath } = entries[fileIndex];
          const chunkCount = Math.ceil(file.size / chunkSize);
          for (let chunkIndex = 0; chunkIndex < chunkCount; chunkIndex += 1) {
            const start = chunkIndex * chunkSize;
            const end = Math.min(file.size, start + chunkSize);
            const chunkForm = new FormData();
            chunkForm.append("upload_id", uploadId);
            chunkForm.append("file_index", String(fileIndex));
            chunkForm.append("chunk_index", String(chunkIndex));
            chunkForm.append("csrf_token", csrfTokenForForm(form));
            chunkForm.append("chunk", file.slice(start, end), `${file.name}.part${chunkIndex}`);

            const percent = totalBytes ? (uploadedBytes / totalBytes) * 100 : 0;
            setUploadStatus(form, {
              text: `Uploading ${relativePath}`,
              count: `${uploadedChunks + 1} of ${totalChunks} chunks`,
              percent,
              hidden: false,
            });

            const chunkResponse = await fetch(form.dataset.chunkUrl, {
              method: "POST",
              headers: { Accept: "application/json" },
              body: chunkForm,
            });
            const chunkPayload = await responsePayload(chunkResponse);
            if (!chunkResponse.ok || chunkPayload.error) {
              throw new Error(chunkPayload.error || `Chunk upload failed for ${relativePath}.`);
            }
            uploadedBytes += end - start;
            uploadedChunks += 1;
          }
        }

        setUploadStatus(form, { text: "Rebuilding package on server...", count: "", percent: 100, hidden: false });
        const completeResponse = await fetch(form.dataset.completeUrl, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ upload_id: uploadId, csrf_token: csrfTokenForForm(form) }),
        });
        const completePayload = await responsePayload(completeResponse);
        if (!completeResponse.ok || completePayload.error) {
          throw new Error(completePayload.error || "Upload could not be completed.");
        }
        completed = true;
        window.removeEventListener("beforeunload", abortOnUnload);
        window.location.href = completePayload.redirect_url || window.location.href;
      } catch (error) {
        await abortUpload(form, uploadId);
        setUploadStatus(form, { text: error.message || "Upload failed.", count: "", percent: 0, hidden: false });
        window.alert(error.message || "Upload failed.");
        if (button) {
          button.disabled = false;
          button.textContent = originalButtonText;
        }
      } finally {
        window.removeEventListener("beforeunload", abortOnUnload);
      }
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

function bindCropAdjustment() {
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  document.querySelectorAll(".js-crop-adjust-wrap[data-crop-adjust-url]").forEach((wrap) => {
    const image = wrap.querySelector(".js-crop-adjust-image");
    const layer = wrap.querySelector(".js-crop-adjust-layer");
    const rect = wrap.querySelector(".js-crop-adjust-rect");
    const controls = wrap.closest(".cockpit-layout")?.querySelector(".js-crop-adjust-controls") || document.querySelector(".js-crop-adjust-controls");
    if (!image || !layer || !rect || !controls) return;

    const startButton = controls.querySelector("[data-crop-adjust-start]");
    const saveButton = controls.querySelector("[data-crop-adjust-save]");
    const cancelButton = controls.querySelector("[data-crop-adjust-cancel]");
    const status = controls.querySelector("[data-crop-adjust-status]");
    const minSize = 8;
    let active = false;
    let box = {
      x: Number(wrap.dataset.cropX || 0),
      y: Number(wrap.dataset.cropY || 0),
      w: Number(wrap.dataset.cropW || 0),
      h: Number(wrap.dataset.cropH || 0),
    };
    let savedBox = { ...box };
    let drag = null;

    const setStatus = (text = "") => {
      if (status) status.textContent = text;
    };

    const displayScale = () => ({
      x: image.clientWidth / Math.max(image.naturalWidth || 1, 1),
      y: image.clientHeight / Math.max(image.naturalHeight || 1, 1),
    });

    const pointerScale = () => {
      const imageRect = image.getBoundingClientRect();
      return {
        x: imageRect.width / Math.max(image.naturalWidth || 1, 1),
        y: imageRect.height / Math.max(image.naturalHeight || 1, 1),
      };
    };

    const normalizeBox = (nextBox) => {
      let { x, y, w, h } = nextBox;
      if (w < 0) {
        x += w;
        w = Math.abs(w);
      }
      if (h < 0) {
        y += h;
        h = Math.abs(h);
      }
      const naturalWidth = image.naturalWidth || Number(wrap.dataset.imageWidth || 0) || 1;
      const naturalHeight = image.naturalHeight || Number(wrap.dataset.imageHeight || 0) || 1;
      x = clamp(x, 0, naturalWidth - minSize);
      y = clamp(y, 0, naturalHeight - minSize);
      w = clamp(w, minSize, naturalWidth - x);
      h = clamp(h, minSize, naturalHeight - y);
      return { x, y, w, h };
    };

    const render = () => {
      const scale = displayScale();
      box = normalizeBox(box);
      rect.style.left = `${box.x * scale.x}px`;
      rect.style.top = `${box.y * scale.y}px`;
      rect.style.width = `${box.w * scale.x}px`;
      rect.style.height = `${box.h * scale.y}px`;
    };

    const setMode = (isActive) => {
      active = isActive;
      layer.hidden = !active;
      wrap.classList.toggle("is-adjusting", active);
      if (startButton) startButton.hidden = active;
      if (saveButton) saveButton.hidden = !active;
      if (cancelButton) cancelButton.hidden = !active;
      if (active) {
        savedBox = { ...box };
        render();
        setStatus("");
      }
    };

    const updateFromPointer = (event) => {
      if (!drag) return;
      event.preventDefault();
      event.stopPropagation();
      const scale = pointerScale();
      const dx = (event.clientX - drag.startClientX) / Math.max(scale.x, 0.001);
      const dy = (event.clientY - drag.startClientY) / Math.max(scale.y, 0.001);
      const start = drag.startBox;
      let next = { ...start };
      if (drag.handle === "move") {
        next.x = start.x + dx;
        next.y = start.y + dy;
      } else {
        const left = start.x;
        const top = start.y;
        const right = start.x + start.w;
        const bottom = start.y + start.h;
        const nextLeft = drag.handle.includes("w") ? left + dx : left;
        const nextRight = drag.handle.includes("e") ? right + dx : right;
        const nextTop = drag.handle.includes("n") ? top + dy : top;
        const nextBottom = drag.handle.includes("s") ? bottom + dy : bottom;
        next = {
          x: nextLeft,
          y: nextTop,
          w: nextRight - nextLeft,
          h: nextBottom - nextTop,
        };
      }
      box = normalizeBox(next);
      render();
    };

    const endDrag = (event) => {
      if (!drag) return;
      if (rect.hasPointerCapture(event.pointerId)) {
        rect.releasePointerCapture(event.pointerId);
      }
      drag = null;
      render();
    };

    rect.addEventListener("pointerdown", (event) => {
      if (!active || event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      drag = {
        handle: event.target?.dataset?.cropHandle || "move",
        startClientX: event.clientX,
        startClientY: event.clientY,
        startBox: { ...box },
      };
      rect.setPointerCapture(event.pointerId);
    });
    rect.addEventListener("pointermove", updateFromPointer);
    rect.addEventListener("pointerup", endDrag);
    rect.addEventListener("pointercancel", endDrag);

    if (startButton) {
      startButton.addEventListener("click", () => setMode(true));
    }
    if (cancelButton) {
      cancelButton.addEventListener("click", () => {
        box = { ...savedBox };
        setMode(false);
        render();
        setStatus("");
      });
    }
    if (saveButton) {
      saveButton.addEventListener("click", async () => {
        saveButton.disabled = true;
        setStatus("Updating...");
        try {
          const response = await fetch(wrap.dataset.cropAdjustUrl, {
            method: "POST",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              csrf_token: csrfToken(),
              crop_box: [box.x, box.y, box.w, box.h],
            }),
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok || payload.error) {
            throw new Error(payload.error || "Crop update failed.");
          }
          if (Array.isArray(payload.crop_box) && payload.crop_box.length === 4) {
            box = {
              x: Number(payload.crop_box[0]),
              y: Number(payload.crop_box[1]),
              w: Number(payload.crop_box[2]),
              h: Number(payload.crop_box[3]),
            };
            savedBox = { ...box };
          }
          if (payload.image_url) {
            image.addEventListener("load", render, { once: true });
            image.src = `${payload.image_url}${payload.image_url.includes("?") ? "&" : "?"}t=${Date.now()}`;
          }
          setMode(false);
          setStatus("Crop updated.");
          window.setTimeout(() => setStatus(""), 2200);
        } catch (error) {
          setStatus(error.message || "Crop update failed.");
        } finally {
          saveButton.disabled = false;
        }
      });
    }
    if (image.complete) render();
    image.addEventListener("load", render);
    window.addEventListener("resize", render);
  });
}

function bindGeometryCorrection() {
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  document.querySelectorAll(".js-crop-adjust-wrap[data-geometry-correction-url]").forEach((wrap) => {
    const image = wrap.querySelector(".js-crop-adjust-image");
    const layer = wrap.querySelector(".js-geometry-correct-layer");
    const controls = wrap.closest(".cockpit-layout")?.querySelector(".js-geometry-correct-controls");
    if (!image || !layer || !controls) return;

    const startButtons = controls.querySelectorAll("[data-geometry-start]");
    const saveButtons = controls.querySelectorAll("[data-geometry-save]");
    const deleteButton = controls.querySelector("[data-geometry-delete]");
    const cancelButton = controls.querySelector("[data-geometry-cancel]");
    const status = controls.querySelector("[data-geometry-status]");
    const minSize = 8;
    let activeMode = "";
    let boxes = [];
    let selectedIndex = -1;
    let drag = null;

    const setStatus = (text = "") => {
      if (status) status.textContent = text;
    };

    const naturalSize = () => ({
      width: image.naturalWidth || 1,
      height: image.naturalHeight || 1,
    });

    const displayScale = () => {
      const size = naturalSize();
      return {
        x: image.clientWidth / Math.max(size.width, 1),
        y: image.clientHeight / Math.max(size.height, 1),
      };
    };

    const pointerScale = () => {
      const rect = image.getBoundingClientRect();
      const size = naturalSize();
      return {
        x: rect.width / Math.max(size.width, 1),
        y: rect.height / Math.max(size.height, 1),
        left: rect.left,
        top: rect.top,
      };
    };

    const pointFromEvent = (event) => {
      const scale = pointerScale();
      return {
        x: (event.clientX - scale.left) / Math.max(scale.x, 0.001),
        y: (event.clientY - scale.top) / Math.max(scale.y, 0.001),
      };
    };

    const normalizeBox = (box) => {
      let { x, y, w, h } = box;
      if (w < 0) {
        x += w;
        w = Math.abs(w);
      }
      if (h < 0) {
        y += h;
        h = Math.abs(h);
      }
      const size = naturalSize();
      x = clamp(x, 0, Math.max(size.width - minSize, 0));
      y = clamp(y, 0, Math.max(size.height - minSize, 0));
      w = clamp(w, minSize, size.width - x);
      h = clamp(h, minSize, size.height - y);
      return { x, y, w, h };
    };

    const startDrag = (event, index, handle) => {
      if (!activeMode || event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      selectedIndex = index;
      const point = pointFromEvent(event);
      drag = {
        type: handle === "draw" ? "draw" : handle === "move" ? "move" : "resize",
        handle,
        index,
        startPoint: point,
        startBox: boxes[index] ? { ...boxes[index] } : { x: point.x, y: point.y, w: 0, h: 0 },
      };
      if (handle === "draw") {
        boxes.push({ ...drag.startBox });
        drag.index = boxes.length - 1;
        selectedIndex = drag.index;
      }
      render();
    };

    const render = () => {
      const scale = displayScale();
      layer.innerHTML = "";
      boxes = boxes.map(normalizeBox);
      boxes.forEach((box, index) => {
        const rect = document.createElement("div");
        rect.className = `geometry-correct-rect${index === selectedIndex ? " selected" : ""}`;
        rect.style.left = `${box.x * scale.x}px`;
        rect.style.top = `${box.y * scale.y}px`;
        rect.style.width = `${box.w * scale.x}px`;
        rect.style.height = `${box.h * scale.y}px`;
        rect.dataset.geometryIndex = String(index);
        rect.innerHTML = `
          <span class="geometry-correct-label">${index + 1}</span>
          <span class="geometry-correct-handle geometry-correct-handle-nw" data-geometry-handle="nw"></span>
          <span class="geometry-correct-handle geometry-correct-handle-ne" data-geometry-handle="ne"></span>
          <span class="geometry-correct-handle geometry-correct-handle-sw" data-geometry-handle="sw"></span>
          <span class="geometry-correct-handle geometry-correct-handle-se" data-geometry-handle="se"></span>
        `;
        rect.addEventListener("pointerdown", (event) => {
          const handle = event.target?.dataset?.geometryHandle || "move";
          startDrag(event, index, handle);
        });
        layer.appendChild(rect);
      });
      if (deleteButton) deleteButton.hidden = !activeMode || selectedIndex < 0;
    };

    const setMode = (mode) => {
      activeMode = mode;
      boxes = [];
      selectedIndex = -1;
      layer.hidden = !activeMode;
      wrap.classList.toggle("is-geometry-correcting", Boolean(activeMode));
      startButtons.forEach((button) => { button.hidden = Boolean(activeMode); });
      saveButtons.forEach((button) => { button.hidden = !activeMode || button.dataset.geometrySave !== activeMode; });
      if (cancelButton) cancelButton.hidden = !activeMode;
      if (deleteButton) deleteButton.hidden = true;
      setStatus(activeMode ? "Draw boxes on the crop." : "");
      render();
    };

    const updateDrag = (event) => {
      if (!drag) return;
      event.preventDefault();
      const point = pointFromEvent(event);
      const dx = point.x - drag.startPoint.x;
      const dy = point.y - drag.startPoint.y;
      const start = drag.startBox;
      let next = { ...start };
      if (drag.type === "draw") {
        next = { x: start.x, y: start.y, w: dx, h: dy };
      } else if (drag.type === "move") {
        next = { ...start, x: start.x + dx, y: start.y + dy };
      } else {
        const left = start.x;
        const top = start.y;
        const right = start.x + start.w;
        const bottom = start.y + start.h;
        next = {
          x: drag.handle.includes("w") ? left + dx : left,
          y: drag.handle.includes("n") ? top + dy : top,
          w: (drag.handle.includes("e") ? right + dx : right) - (drag.handle.includes("w") ? left + dx : left),
          h: (drag.handle.includes("s") ? bottom + dy : bottom) - (drag.handle.includes("n") ? top + dy : top),
        };
      }
      boxes[drag.index] = normalizeBox(next);
      render();
    };

    const endDrag = () => {
      if (!drag) return;
      boxes = boxes.filter((box) => box.w >= minSize && box.h >= minSize);
      selectedIndex = Math.min(selectedIndex, boxes.length - 1);
      drag = null;
      render();
    };

    layer.addEventListener("pointerdown", (event) => {
      if (!activeMode || event.button !== 0 || event.target !== layer) return;
      startDrag(event, boxes.length, "draw");
    });
    window.addEventListener("pointermove", updateDrag);
    window.addEventListener("pointerup", endDrag);
    window.addEventListener("pointercancel", endDrag);

    startButtons.forEach((button) => {
      button.addEventListener("click", () => setMode(button.dataset.geometryStart || ""));
    });
    if (cancelButton) {
      cancelButton.addEventListener("click", () => setMode(""));
    }
    if (deleteButton) {
      deleteButton.addEventListener("click", () => {
        if (selectedIndex < 0) return;
        boxes.splice(selectedIndex, 1);
        selectedIndex = Math.min(selectedIndex, boxes.length - 1);
        render();
      });
    }
    saveButtons.forEach((button) => {
      button.addEventListener("click", async () => {
        const mode = button.dataset.geometrySave || activeMode;
        if (mode === "overmerge" && boxes.length < 2) {
          setStatus("Draw at least two boxes.");
          return;
        }
        if (mode === "partial" && boxes.length !== 1) {
          setStatus("Draw one box.");
          return;
        }
        button.disabled = true;
        setStatus("Saving...");
        try {
          const response = await fetch(wrap.dataset.geometryCorrectionUrl, {
            method: "POST",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              csrf_token: csrfToken(),
              mode,
              crop_boxes: boxes.map((box) => [box.x, box.y, box.w, box.h]),
              queue_status: controls.dataset.queueStatus || "pending",
              search_query: controls.dataset.searchQuery || "",
              attention_only: controls.dataset.attentionOnly || "0",
            }),
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok || payload.error) {
            throw new Error(payload.error || "Correction failed.");
          }
          if (payload.redirect_url) {
            window.location.href = payload.redirect_url;
          }
        } catch (error) {
          setStatus(error.message || "Correction failed.");
        } finally {
          button.disabled = false;
        }
      });
    });
    if (image.complete) render();
    image.addEventListener("load", render);
    window.addEventListener("resize", render);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  applyBoundingBoxes();
  bindQueueSelection();
  bindBulkReviewForms();
  bindProjectDeleteDialog();
  bindReviewShortcuts();
  bindChunkedUploadForms();
  bindPopulateWorkspace();
  bindGenerateForms();
  bindFilePickerSummaries();
  bindFolderDialogs();
  bindPanZoomViewers();
  bindCropAdjustment();
  bindGeometryCorrection();
});
