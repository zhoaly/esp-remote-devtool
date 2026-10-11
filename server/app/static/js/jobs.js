function appendJobCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = String(value ?? "");
    row.appendChild(cell);
}

function appendJobActions(row, job) {
    const cell = document.createElement("td");
    const links = [];
    if (job.download_url) {
        const download = document.createElement("a");
        download.href = REMOTE_BASE + job.download_url;
        download.target = "_blank";
        download.rel = "noopener";
        download.textContent = "下载";
        links.push(download);
    }
    if (job.log_url) {
        const log = document.createElement("a");
        log.href = REMOTE_BASE + job.log_url;
        log.target = "_blank";
        log.rel = "noopener";
        log.textContent = "日志 JSON";
        links.push(log);
    }
    links.forEach((link, index) => {
        if (index) cell.append(" / ");
        cell.appendChild(link);
    });
    if (!links.length) cell.textContent = "-";
    row.appendChild(cell);
}

async function loadJobs() {
    const box = document.getElementById("jobsBody");
    try {
        const jobs = (await apiGet("/jobs?kind=esp")).filter(isEspFirmwareJob);
        box.replaceChildren();
        jobs.forEach((job) => {
            const row = document.createElement("tr");
            appendJobCell(row, job.id);
            appendJobCell(row, job.status);
            appendJobCell(row, job.project_name);
            appendJobCell(row, job.target);
            appendJobCell(row, job.created_at);
            appendJobCell(row, job.finished_at);
            appendJobActions(row, job);
            box.appendChild(row);
        });
    } catch (err) {
        box.replaceChildren();
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 7;
        cell.textContent = `加载失败：${err.message}`;
        row.appendChild(cell);
        box.appendChild(row);
    }
}

document.addEventListener("DOMContentLoaded", loadJobs);
