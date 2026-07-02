let remoteWorkspaces = [];
function handleSourceModeChange() {
            const sourceMode = document.getElementById("sourceMode").value;
            const isRemoteWorkspace = sourceMode === "remote_workspace";
            document.getElementById("remoteWorkspaceField").style.display = isRemoteWorkspace ? "grid" : "none";
            document.querySelectorAll(".local-upload-field").forEach((field) => {
                field.style.display = isRemoteWorkspace ? "none" : "grid";
            });
        }

        function renderWorkspaces(workspaces) {
            const select = document.getElementById("remoteWorkspace");
            const hint = document.getElementById("remoteWorkspaceHint");
            select.innerHTML = "";

            if (!workspaces.length) {
                const opt = document.createElement("option");
                opt.value = "";
                opt.textContent = "未配置可用远端工作区";
                select.appendChild(opt);
                hint.textContent = "远端 Server 当前没有返回可用工作区，请检查 server/config/workspaces.json。";
                return;
            }

            workspaces.forEach((workspace) => {
                const opt = document.createElement("option");
                opt.value = workspace.workspace_id;
                opt.textContent = `${workspace.display_name || workspace.workspace_id} (${workspace.target || "unknown"})`;
                opt.dataset.projectName = workspace.project_name || "";
                opt.dataset.idfImage = workspace.idf_image || "";
                opt.dataset.target = workspace.target || "";
                select.appendChild(opt);
            });

            hint.textContent = "远端固定工作区构建会直接使用服务器白名单路径，不会读取 Windows 本地工程路径。";
        }

        async function loadWorkspaces() {
            try {
                const data = await apiGet("/api/workspaces");
                remoteWorkspaces = data.workspaces || [];
                renderWorkspaces(remoteWorkspaces);
            } catch (err) {
                remoteWorkspaces = [];
                renderWorkspaces([]);
                document.getElementById("remoteWorkspaceHint").textContent = `加载远端工作区失败: ${err.message}`;
            }
        }

        function setBuildStatus(text, type = "") {
            const box = document.getElementById("buildStatusBox");
            box.className = "status";
            if (type) box.classList.add(type);
            box.textContent = text;
        }

        function setFlashStatus(text, type = "") {
            const box = document.getElementById("flashStatusBox");
            box.className = "status";
            if (type) box.classList.add(type);
            box.textContent = text;
        }

        function setOtaStatus(text, type = "") {
            const box = document.getElementById("otaStatusBox");
            box.className = "status";
            if (type) box.classList.add(type);
            box.textContent = text;
        }

        function setLinks(downloadUrl, logUrl) {
            const area = document.getElementById("linkArea");
            area.innerHTML = "";

            if (downloadUrl) {
                const download = document.createElement("a");
                download.href = REMOTE_BASE + downloadUrl;
                download.target = "_blank";
                download.textContent = "下载固件包";
                area.appendChild(download);
            }

            if (logUrl) {
                const log = document.createElement("a");
                log.href = REMOTE_BASE + logUrl;
                log.target = "_blank";
                log.textContent = "打开完整构建日志";
                area.appendChild(log);
            }
        }

        async function parseErrorResponse(resp) {
            const text = await resp.text();
            try {
                const data = JSON.parse(text);
                return typeof data.detail === "string"
                    ? data.detail
                    : JSON.stringify(data.detail || data, null, 2);
            } catch {
                return text || `HTTP ${resp.status}`;
            }
        }

        function stopPolling() {
            if (pollTimer) {
                clearInterval(pollTimer);
                pollTimer = null;
            }
        }

        async function startBuild() {
            const startBtn = document.getElementById("startBtn");
            const flashBtn = document.getElementById("flashBtn");
            const sourceMode = document.getElementById("sourceMode").value;

            startBtn.disabled = true;
            if (flashBtn) flashBtn.disabled = true;
            stopPolling();

            currentJobId = null;
            currentDownloadUrl = null;
            currentJob = null;
            currentManifestUrl = null;
            document.getElementById("otaPublishBtn").disabled = true;
            setOtaStatus("等待构建成功后发布 OTA。");
            document.getElementById("jobIdCard").textContent = "starting";
            setText("flashLogBox", "暂无烧录日志。");
            setFlashStatus("等待构建成功后烧录。");
            setLinks(null, null);

            try {
                let resp;
                let successMessage;

                if (sourceMode === "remote_workspace") {
                    const workspaceId = document.getElementById("remoteWorkspace").value;
                    if (!workspaceId) {
                        throw new Error("请选择可用的远端工作区");
                    }

                    document.getElementById("buildLogBox").textContent = "准备调用远端工作区构建接口...";
                    setBuildStatus("正在请求远端 Server 直接从固定工作区构建...");

                    resp = { ok: true, json: async () => await apiPostJson("/api/build/workspace", { workspace_id: workspaceId }) };
                    successMessage = "远端工作区构建已启动，开始轮询远端构建状态...";
                } else {
                    document.getElementById("buildLogBox").textContent = "准备调用本地 Agent...";
                    setBuildStatus("正在请求本地 Agent 压缩源码并上传到远端服务器...");

                    const payload = {
                        project_path: document.getElementById("projectPath").value.trim(),
                        project_name: document.getElementById("projectName").value.trim(),
                        idf_image: document.getElementById("idfImage").value.trim(),
                        target: document.getElementById("target").value
                    };

                    resp = { ok: true, json: async () => await localAgentPostJson("/api/build_from_path", payload) };
                    successMessage = "源码已上传，开始轮询远端构建状态...";
                }

                if (!resp.ok) {
                    throw new Error(await parseErrorResponse(resp));
                }

                const data = await resp.json();
                currentJobId = sourceMode === "remote_workspace"
                    ? data.job_id
                    : data.remote_response?.job_id;

                if (!currentJobId) {
                    throw new Error(sourceMode === "remote_workspace"
                        ? "远端 Server 返回中缺少 job_id"
                        : "本地 Agent 返回中缺少 remote_response.job_id");
                }

                document.getElementById("jobIdCard").textContent = currentJobId;
                setBuildStatus([
                    successMessage,
                    `Job ID: ${currentJobId}`
                ].join("\n"));

                await pollJob();
                pollTimer = setInterval(pollJob, 3000);
            } catch (err) {
                setBuildStatus(`启动构建失败\n${err.message}`, "failed");
                document.getElementById("jobIdCard").textContent = "error";
                startBtn.disabled = false;
            }
        }

        async function pollJob() {
            if (!currentJobId) return;

            try {
                const job = await apiGet("/api/jobs/" + currentJobId);
                currentJob = job;
                document.getElementById("jobIdCard").textContent = job.job_id;
                setBuildStatus([
                    `Job ID: ${job.job_id}`,
                    `状态: ${job.status}`,
                    `消息: ${job.message}`,
                    `项目: ${job.project_name}`,
                    `Target: ${job.target}`,
                    `IDF Image: ${job.idf_image}`
                ].join("\n"), job.status === "success" ? "success" : job.status === "failed" ? "failed" : "");

                refreshBuildLog();

                if (job.status === "success") {
                    stopPolling();
                    currentDownloadUrl = REMOTE_BASE + job.download_url;
                    setLinks(job.download_url, job.log_url);
                    document.getElementById("startBtn").disabled = false;
                    const flashBtnDone = document.getElementById("flashBtn");
                    if (flashBtnDone) flashBtnDone.disabled = false;
                    document.getElementById("otaPublishBtn").disabled = !job.ota_publishable;
                    document.getElementById("otaVersion").value = job.project_version || "";
                    setOtaStatus([
                        `OTA 可发布: ${job.ota_publishable}`,
                        `App Bin: ${job.ota_app_bin_name || "未识别"}`,
                        `App Size: ${job.ota_app_size || 0} bytes`,
                        `App SHA256: ${job.ota_app_sha256 || ""}`,
                        job.ota_publishable ? "可点击发布为 OTA Release。" : "App 超出 OTA 分区限制或不可发布。"
                    ].join("\n"), job.ota_publishable ? "success" : "failed");
                    refreshSerialPorts();
                }

                if (job.status === "failed") {
                    stopPolling();
                    setLinks(null, job.log_url);
                    document.getElementById("startBtn").disabled = false;
                    const flashBtnFailed = document.getElementById("flashBtn");
                    if (flashBtnFailed) flashBtnFailed.disabled = true;
                }
            } catch (err) {
                setBuildStatus(`轮询构建状态失败\n${err.message}`, "failed");
                document.getElementById("startBtn").disabled = false;
            }
        }

        async function refreshBuildLog() {
            if (!currentJobId) return;

            try {
                const text = await apiGetText("/api/logs/" + currentJobId);
                const box = document.getElementById("buildLogBox");
                box.textContent = text || "暂无构建日志。";
                box.scrollTop = box.scrollHeight;
            } catch {
            }
        }

document.addEventListener("DOMContentLoaded", () => { if (document.getElementById("sourceMode")) { loadWorkspaces(); handleSourceModeChange(); } });
