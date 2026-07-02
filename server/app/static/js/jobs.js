async function loadJobs() {
    const box = document.getElementById("jobsBody");
    try {
        const jobs = await apiGet("/api/jobs");
        box.innerHTML = "";
        jobs.forEach((job) => {
            const tr = document.createElement("tr");
            const artifact = job.download_url ? `<a href="${REMOTE_BASE}${job.download_url}" target="_blank">下载</a>` : "-";
            const log = job.log_url ? `<a href="${REMOTE_BASE}${job.log_url}" target="_blank">日志</a>` : "-";
            tr.innerHTML = `<td>${job.job_id || ""}</td><td>${job.status || ""}</td><td>${job.project_name || ""}</td><td>${job.target || ""}</td><td>${job.created_at || ""}</td><td>${job.finished_at || ""}</td><td>${artifact} / ${log}</td>`;
            box.appendChild(tr);
        });
    } catch (err) {
        box.innerHTML = `<tr><td colspan="7">加载失败：${err.message}</td></tr>`;
    }
}
document.addEventListener("DOMContentLoaded", loadJobs);
