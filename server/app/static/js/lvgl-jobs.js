async function loadLvglJobs() {
    const body = document.getElementById("lvglJobsBody");
    if (!body) return;

    body.innerHTML = '<tr><td colspan="8">Loading...</td></tr>';

    try {
        const jobs = await apiGet("/api/lvgl/jobs");
        if (!jobs.length) {
            body.innerHTML = '<tr><td colspan="8">No LVGL build history yet.</td></tr>';
            return;
        }

        body.innerHTML = "";
        jobs.forEach((job) => {
            const preview = job.preview_url ? `<a href="${lvglPreviewPageUrl(job.job_id)}">Preview</a>` : "-";
            const artifactUrl = job.artifact_url || job.download_url;
            const download = artifactUrl ? `<a href="${REMOTE_BASE}${artifactUrl}" target="_blank">Download</a>` : "-";
            const log = job.log_url ? `<a href="${REMOTE_BASE}${job.log_url}" target="_blank">Log</a>` : "-";
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td title="${lvglEscapeHtml(job.job_id || "")}">${lvglEscapeHtml(job.job_id || "")}</td>
                <td>${lvglStatusBadge(job)}</td>
                <td>${lvglEscapeHtml(job.project_name || "")}</td>
                <td>${lvglEscapeHtml(lvglJobDimensions(job))}</td>
                <td>${lvglEscapeHtml(job.source_mode || "")}</td>
                <td>${lvglEscapeHtml(job.created_at || "")}</td>
                <td>${lvglEscapeHtml(job.finished_at || "")}</td>
                <td class="job-actions">${preview} / ${download} / ${log}</td>
            `;
            body.appendChild(tr);
        });
    } catch (err) {
        body.innerHTML = `<tr><td colspan="8">Failed to load LVGL build history: ${lvglEscapeHtml(err.message)}</td></tr>`;
    }
}

document.addEventListener("DOMContentLoaded", loadLvglJobs);
