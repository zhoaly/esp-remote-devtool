async function refreshSerialPorts() {
            const select = document.getElementById("serialPort");

            try {
                setFlashStatus("正在从本地 Agent 获取串口列表...");
                const data = await localAgentGet("/api/serial_ports");
                select.innerHTML = "";

                if (!data.ports || data.ports.length === 0) {
                    const opt = document.createElement("option");
                    opt.value = "";
                    opt.textContent = "未发现可用串口";
                    select.appendChild(opt);
                    setFlashStatus("未自动发现串口，请确认设备连接后重新刷新串口。", "failed");
                    return;
                }

                data.ports.forEach((port) => {
                    const opt = document.createElement("option");
                    opt.value = port.device;
                    opt.textContent = `${port.device} - ${port.description}`;
                    select.appendChild(opt);
                });

                const defaultPort = data.default_port || data.ports[0].device;
                select.value = defaultPort;
                setFlashStatus(`串口刷新成功，当前选择: ${defaultPort}`, "success");
            } catch (err) {
                setFlashStatus([
                    "刷新串口失败",
                    err.message,
                    "",
                    "请确认本地 Agent 正在运行: http://127.0.0.1:8765"
                ].join("\n"), "failed");
            }
        }

        async function flashFirmware() {
            const artifactInput = document.getElementById("artifactUrl");
            if (artifactInput && artifactInput.value.trim()) currentDownloadUrl = artifactInput.value.trim();
            if (!currentDownloadUrl) {
                setFlashStatus("没有可烧录的固件，请先输入 Artifact URL。", "failed");
                return;
            }

            const flashBtn = document.getElementById("flashBtn");
            flashBtn.disabled = true;

            const comPort = document.getElementById("serialPort").value.trim();
            if (!comPort) {
                setFlashStatus("请选择一个可用串口后再烧录。", "failed");
                flashBtn.disabled = false;
                return;
            }
            const baud = parseInt(document.getElementById("flashBaud").value || "460800", 10);
            const chip = document.getElementById("flashChip").value.trim() || "esp32s3";

            setFlashStatus([
                "开始烧录",
                `固件: ${currentDownloadUrl}`,
                `串口: ${comPort}`,
                `波特率: ${baud}`,
                `芯片: ${chip}`
            ].join("\n"));
            document.getElementById("flashLogBox").textContent = "正在下载固件并调用 esptool，请稍候...";

            try {
                const data = await localAgentPostJson("/api/flash_from_artifact", { artifact_url: currentDownloadUrl, com_port: comPort, baud, chip });
                setFlashStatus([
                    "烧录成功",
                    `串口: ${data.com_port}`,
                    `波特率: ${data.baud}`
                ].join("\n"), "success");
                document.getElementById("flashLogBox").textContent = data.log || "Flash success";
            } catch (err) {
                setFlashStatus(`烧录失败\n${err.message}`, "failed");
                document.getElementById("flashLogBox").textContent = err.message;
            } finally {
                flashBtn.disabled = false;
            }
        }
