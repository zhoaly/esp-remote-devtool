async function loadLvglJobs() {
    const body = document.getElementById("lvglJobsBody");
    if (!body) return;

    body.innerHTML = '<tr><td colspan="8">加载中...</td></tr>';

    try {
        const jobs = await apiGet("/api/lvgl/jobs");
        if (!jobs.length) {
            body.innerHTML = '<tr><td colspan="8">暂无 LVGL 构建历史。</td></tr>';
            return;
        }

        body.innerHTML = "";
        jobs.forEach((job) => {
            const preview = job.preview_url ? `<a href="${lvglPreviewPageUrl(job.job_id)}">预览</a>` : "-";
            const artifactUrl = job.artifact_url || job.download_url;
            const download = artifactUrl ? `<a href="${REMOTE_BASE}${artifactUrl}" target="_blank">下载</a>` : "-";
            const log = job.log_url ? `<a href="${REMOTE_BASE}${job.log_url}" target="_blank">日志</a>` : "-";
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
        body.innerHTML = `<tr><td colspan="8">加载 LVGL 构建历史失败：${lvglEscapeHtml(err.message)}</td></tr>`;
    }
}

document.addEventListener("DOMContentLoaded", loadLvglJobs);
