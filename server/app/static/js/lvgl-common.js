function lvglEscapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function isLvglPreviewJob(job) {
    return job?.tool_type === "lvgl_simulator" && job.status === "success" && Boolean(job.preview_url);
}

function lvglStatusBadge(job) {
    const status = job?.status || "?";
    const cls = status === "success" ? "tag success" : status === "failed" ? "tag failed" : "tag";
    return `<span class="${cls}">${lvglEscapeHtml(status)}</span>`;
}

function lvglJobDimensions(job) {
    return job?.width && job?.height ? `${job.width} x ${job.height}` : "-";
}

function lvglPreviewPageUrl(jobId) {
    return `/tools/lvgl/preview${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ""}`;
}

function stripEmscriptenChrome(frame) {
    try {
        const doc = frame.contentDocument || frame.contentWindow.document;
        if (!doc) return;
        const style = doc.createElement("style");
        style.textContent = `
            #emscripten_logo { display: none !important; }
            #controls       { display: none !important; }
            #output         { display: none !important; }
            body            { margin: 0; padding: 0; background: transparent; overflow: hidden; }
            .emscripten_border {
                border: none !important;
                display: flex !important;
                align-items: center;
                justify-content: center;
            }
        `;
        doc.head.appendChild(style);
    } catch (_) {
    }
}
