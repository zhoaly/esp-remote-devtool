function appendLvglJobCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = String(value ?? "");
    row.appendChild(cell);
    return cell;
}

function appendLvglJobStatus(row, job) {
    const cell = document.createElement("td");
    const badge = document.createElement("span");
    const status = String(job.status || "?");
    badge.className = status === "succeeded"
        ? "tag success"
        : status === "failed"
            ? "tag failed"
            : "tag";
    badge.textContent = status === "succeeded" ? "成功" : status === "failed" ? "失败" : status;
    cell.appendChild(badge);
    row.appendChild(cell);
}

function appendLvglJobActions(row, job) {
    const cell = document.createElement("td");
    cell.className = "job-actions";
    const actions = [];
    const artifactUrl = job.artifact_url || job.download_url;
    const definitions = [
        [job.preview_url ? lvglPreviewPageUrl(job.id) : "", "预览"],
        [artifactUrl ? REMOTE_BASE + artifactUrl : "", "下载"],
        [job.log_url ? REMOTE_BASE + job.log_url : "", "日志 JSON"],
    ];
    definitions.forEach(([href, label]) => {
        if (!href) return;
        const link = document.createElement("a");
        link.href = href;
        link.textContent = label;
        if (label !== "预览") {
            link.target = "_blank";
            link.rel = "noopener";
        }
        actions.push(link);
    });
    actions.forEach((link, index) => {
        if (index) cell.append(" / ");
        cell.appendChild(link);
    });
    if (!actions.length) cell.textContent = "-";
    row.appendChild(cell);
}

function renderLvglJobsMessage(body, message) {
    body.replaceChildren();
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 8;
    cell.textContent = message;
    row.appendChild(cell);
    body.appendChild(row);
}

async function loadLvglJobs() {
    const body = document.getElementById("lvglJobsBody");
    if (!body) return;

    renderLvglJobsMessage(body, "加载中...");
    try {
        const jobs = await apiGet("/jobs?kind=lvgl");
        if (!jobs.length) {
            renderLvglJobsMessage(body, "暂无 LVGL 构建历史。");
            return;
        }

        body.replaceChildren();
        jobs.forEach((job) => {
            const row = document.createElement("tr");
            const idCell = appendLvglJobCell(row, job.id);
            idCell.title = String(job.id || "");
            appendLvglJobStatus(row, job);
            appendLvglJobCell(row, job.project_name);
            appendLvglJobCell(row, lvglJobDimensions(job));
            appendLvglJobCell(row, job.source_mode);
            appendLvglJobCell(row, job.created_at);
            appendLvglJobCell(row, job.finished_at);
            appendLvglJobActions(row, job);
            body.appendChild(row);
        });
    } catch (err) {
        renderLvglJobsMessage(body, `加载 LVGL 构建历史失败：${err.message}`);
    }
}

document.addEventListener("DOMContentLoaded", loadLvglJobs);
