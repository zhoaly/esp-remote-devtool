async function publishOtaRelease() {
            if (!currentJobId || !currentJob) {
                setOtaStatus("没有可发布的构建任务。", "failed");
                return;
            }
            const btn = document.getElementById("otaPublishBtn");
            btn.disabled = true;
            try {
                const payload = {
                    channel: document.getElementById("otaChannel").value,
                    version: document.getElementById("otaVersion").value.trim(),
                    min_version: document.getElementById("otaMinVersion").value.trim(),
                    force: document.getElementById("otaForce").value === "true",
                    release_notes: document.getElementById("otaReleaseNotes").value.trim()
                };
                const data = await apiPostJson("/api/ota/publish/" + currentJobId, payload);
                currentManifestUrl = data.manifest_url;
                setOtaStatus([
                    "OTA 发布成功",
                    `Release ID: ${data.release_id}`,
                    `Manifest URL: ${data.manifest_url}`,
                    `Firmware URL: ${data.firmware_url}`,
                    "",
                    `ota check ${data.manifest_url}`,
                    `ota upgrade_manifest ${data.manifest_url}`
                ].join("\n"), "success");
            } catch (err) {
                setOtaStatus(`OTA 发布失败\n${err.message}`, "failed");
            } finally {
                btn.disabled = false;
            }
        }

        async function copyManifestUrl() {
            if (!currentManifestUrl) {
                setOtaStatus("还没有 Manifest URL，请先发布 OTA Release。", "failed");
                return;
            }
            await navigator.clipboard.writeText(currentManifestUrl);
            setOtaStatus(`已复制 Manifest URL\n${currentManifestUrl}`, "success");
        }
