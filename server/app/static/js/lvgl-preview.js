let lvglPreviewJobs = [];
let currentLvglPreviewUrl = null;
const LVGL_PREVIEW_CHANNEL = "zlyhub.lvgl.preview.v1";
const LVGL_PREVIEW_PROBE_INTERVAL_MS = 250;
const LVGL_PREVIEW_PROBE_LIMIT = 240;
const LVGL_ENCODER_CHANNEL = "zlyhub.lvgl.encoder.v1";
const LVGL_ENCODER_PROBE_INTERVAL_MS = 250;
const LVGL_ENCODER_PROBE_LIMIT = 240;
const LVGL_MOCK_CHANNEL = "zlyhub.lvgl.mock.v1";
const LVGL_MOCK_PROBE_INTERVAL_MS = 250;
const LVGL_MOCK_PROBE_LIMIT = 240;
let lvglEncoderReady = false;
let lvglEncoderPressed = false;
let lvglEncoderProbeTimer = null;
let lvglEncoderProbeAttempts = 0;
let lvglMockReady = false;
let lvglMockProbeTimer = null;
let lvglMockProbeAttempts = 0;
let lvglPreviewReady = false;
let lvglPreviewUsesProtocol = false;
let lvglPreviewProbeTimer = null;
let lvglPreviewProbeAttempts = 0;

function lvglEncoderElements() {
    return {
        card: document.getElementById("lvglEncoderCard"),
        badge: document.getElementById("lvglEncoderBadge"),
        content: document.getElementById("lvglEncoderContent"),
        stateTitle: document.getElementById("lvglEncoderStateTitle"),
        stateMessage: document.getElementById("lvglEncoderStateMessage"),
        hint: document.getElementById("lvglEncoderHint"),
        left: document.getElementById("lvglEncoderLeftBtn"),
        press: document.getElementById("lvglEncoderPressBtn"),
        right: document.getElementById("lvglEncoderRightBtn"),
    };
}

function stopLvglEncoderProbe() {
    if (lvglEncoderProbeTimer) {
        clearInterval(lvglEncoderProbeTimer);
        lvglEncoderProbeTimer = null;
    }
    lvglEncoderProbeAttempts = 0;
}

function setLvglEncoderAvailability(state, hint) {
    const elements = lvglEncoderElements();
    const labels = {
        idle: "未加载",
        loading: "连接中",
        ready: "编码器可用",
        unavailable: "不支持",
        error: "连接失败",
    };
    const titles = {
        idle: "等待预览",
        loading: "正在连接编码器",
        unavailable: "编码器不可用",
        error: "编码器连接失败",
    };
    lvglEncoderReady = state === "ready";

    if (elements.badge) {
        elements.badge.textContent = labels[state] || labels.idle;
        elements.badge.className = "tag";
        if (state === "ready") elements.badge.classList.add("success");
        if (state === "unavailable" || state === "error") {
            elements.badge.classList.add("failed");
        }
    }
    if (elements.card) {
        elements.card.dataset.state = state;
        elements.card.setAttribute(
            "aria-busy",
            String(state === "loading")
        );
    }
    if (elements.content) {
        elements.content.inert = !lvglEncoderReady;
        elements.content.setAttribute(
            "aria-hidden",
            String(!lvglEncoderReady)
        );
    }
    if (elements.stateTitle) {
        elements.stateTitle.textContent = titles[state] || titles.idle;
    }
    if (elements.stateMessage && !lvglEncoderReady) {
        elements.stateMessage.textContent = hint || "";
    }
    if (elements.hint && lvglEncoderReady) {
        elements.hint.textContent = hint || "";
    }
    [elements.left, elements.press, elements.right].forEach((button) => {
        if (button) button.disabled = !lvglEncoderReady;
    });

    if (!lvglEncoderReady && elements.press) {
        lvglEncoderPressed = false;
        elements.press.classList.remove("is-pressed");
        elements.press.setAttribute("aria-pressed", "false");
    }
}

function postLvglEncoderMessage(message) {
    const frame = document.getElementById("lvglPreviewFrame");
    if (!frame?.contentWindow || !currentLvglPreviewUrl) return false;
    frame.contentWindow.postMessage(
        { channel: LVGL_ENCODER_CHANNEL, ...message },
        window.location.origin
    );
    return true;
}

function setLvglEncoderPressed(pressed) {
    if (!lvglEncoderReady || lvglEncoderPressed === pressed) return;
    lvglEncoderPressed = pressed;
    const button = document.getElementById("lvglEncoderPressBtn");
    if (button) {
        button.classList.toggle("is-pressed", pressed);
        button.setAttribute("aria-pressed", String(pressed));
    }
    postLvglEncoderMessage({ action: "press", pressed });
}

function releaseLvglEncoder() {
    if (lvglEncoderPressed) setLvglEncoderPressed(false);
}

function rotateLvglEncoder(steps) {
    if (!lvglEncoderReady || !Number.isInteger(steps) || steps === 0) return;
    postLvglEncoderMessage({ action: "rotate", steps });
}

function resetLvglEncoderBridge(
    state = "idle",
    hint = "请选择支持编码器桥接的构建。"
) {
    releaseLvglEncoder();
    stopLvglEncoderProbe();
    setLvglEncoderAvailability(state, hint);
}

function probeLvglEncoderBridge() {
    if (lvglEncoderReady) {
        stopLvglEncoderProbe();
        return;
    }

    lvglEncoderProbeAttempts += 1;
    postLvglEncoderMessage({ action: "probe" });
    if (lvglEncoderProbeAttempts >= LVGL_ENCODER_PROBE_LIMIT) {
        stopLvglEncoderProbe();
        setLvglEncoderAvailability(
            "unavailable",
            "该构建未提供编码器桥接；原有鼠标预览仍可正常使用。"
        );
    }
}

function startLvglEncoderProbe() {
    resetLvglEncoderBridge("loading", "正在连接预览中的编码器桥接…");
    probeLvglEncoderBridge();
    if (!lvglEncoderReady) {
        lvglEncoderProbeTimer = setInterval(
            probeLvglEncoderBridge,
            LVGL_ENCODER_PROBE_INTERVAL_MS
        );
    }
}

function handleLvglEncoderMessage(event) {
    const frame = document.getElementById("lvglPreviewFrame");
    if (
        event.origin !== window.location.origin ||
        event.source !== frame?.contentWindow ||
        event.data?.channel !== LVGL_ENCODER_CHANNEL ||
        event.data?.action !== "ready"
    ) {
        return;
    }
    if (
        !lvglPreviewReady &&
        detectLvglPreviewProtocol(frame)
    ) {
        return;
    }

    stopLvglEncoderProbe();
    setLvglEncoderAvailability(
        "ready",
        "滚轮或 ←/→ 旋转，Enter/Space 按下；也可使用下方控件。"
    );
}

function bindLvglEncoderControls() {
    const { left, press, right } = lvglEncoderElements();
    if (!left || !press || !right) return;

    left.addEventListener("click", () => rotateLvglEncoder(-1));
    right.addEventListener("click", () => rotateLvglEncoder(1));

    press.addEventListener("pointerdown", (event) => {
        if (!lvglEncoderReady) return;
        event.preventDefault();
        press.setPointerCapture?.(event.pointerId);
        setLvglEncoderPressed(true);
    });
    press.addEventListener("pointerup", (event) => {
        event.preventDefault();
        setLvglEncoderPressed(false);
    });
    press.addEventListener("pointercancel", () => setLvglEncoderPressed(false));
    press.addEventListener("lostpointercapture", () => setLvglEncoderPressed(false));
    press.addEventListener("keydown", (event) => {
        if ((event.key === "Enter" || event.key === " ") && !event.repeat) {
            event.preventDefault();
            setLvglEncoderPressed(true);
        }
    });
    press.addEventListener("keyup", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setLvglEncoderPressed(false);
        }
    });
    press.addEventListener("blur", releaseLvglEncoder);

    window.addEventListener("pointerup", releaseLvglEncoder);
    window.addEventListener("pointercancel", releaseLvglEncoder);
    window.addEventListener("blur", releaseLvglEncoder);
    window.addEventListener("message", handleLvglEncoderMessage);
}

function lvglMockElements() {
    return {
        card: document.getElementById("lvglMockCard"),
        badge: document.getElementById("lvglMockBadge"),
        content: document.getElementById("lvglMockContent"),
        stateTitle: document.getElementById("lvglMockStateTitle"),
        stateMessage: document.getElementById("lvglMockStateMessage"),
        hint: document.getElementById("lvglMockHint"),
        time: document.getElementById("lvglMockTime"),
        timeSynced: document.getElementById("lvglMockTimeSynced"),
        temperature: document.getElementById("lvglMockTemperature"),
        weatherAvailable:
            document.getElementById("lvglMockWeatherAvailable"),
        wifi: document.getElementById("lvglMockWifi"),
        bluetooth: document.getElementById("lvglMockBluetooth"),
        offline: document.getElementById("lvglMockOfflineBtn"),
        connecting: document.getElementById("lvglMockConnectingBtn"),
        online: document.getElementById("lvglMockOnlineBtn"),
        fullyConnected:
            document.getElementById("lvglMockFullyConnectedBtn"),
        apply: document.getElementById("lvglMockApplyBtn"),
        reset: document.getElementById("lvglMockResetBtn"),
        startDemo: document.getElementById("lvglMockStartDemoBtn"),
        stopDemo: document.getElementById("lvglMockStopDemoBtn"),
    };
}

function lvglMockInteractiveElements() {
    const elements = lvglMockElements();
    return [
        elements.time,
        elements.timeSynced,
        elements.temperature,
        elements.weatherAvailable,
        elements.wifi,
        elements.bluetooth,
        elements.offline,
        elements.connecting,
        elements.online,
        elements.fullyConnected,
        elements.apply,
        elements.reset,
        elements.startDemo,
        elements.stopDemo,
    ];
}

function stopLvglMockProbe() {
    if (lvglMockProbeTimer) {
        clearInterval(lvglMockProbeTimer);
        lvglMockProbeTimer = null;
    }
    lvglMockProbeAttempts = 0;
}

function setLvglMockAvailability(state, hint) {
    const elements = lvglMockElements();
    const labels = {
        idle: "未加载",
        loading: "连接中",
        ready: "Mock 可用",
        unavailable: "不支持",
        error: "连接失败",
    };
    const titles = {
        idle: "等待预览",
        loading: "正在连接 Mock Data",
        unavailable: "Mock Data 不可用",
        error: "Mock Data 连接失败",
    };
    lvglMockReady = state === "ready";

    if (elements.badge) {
        elements.badge.textContent = labels[state] || labels.idle;
        elements.badge.className = "tag";
        if (state === "ready") elements.badge.classList.add("success");
        if (state === "unavailable" || state === "error") {
            elements.badge.classList.add("failed");
        }
    }
    if (elements.card) {
        elements.card.dataset.state = state;
        elements.card.setAttribute(
            "aria-busy",
            String(state === "loading")
        );
    }
    if (elements.content) {
        elements.content.inert = !lvglMockReady;
        elements.content.setAttribute(
            "aria-hidden",
            String(!lvglMockReady)
        );
    }
    if (elements.stateTitle) {
        elements.stateTitle.textContent = titles[state] || titles.idle;
    }
    if (elements.stateMessage && !lvglMockReady) {
        elements.stateMessage.textContent = hint || "";
    }
    if (elements.hint && lvglMockReady) {
        elements.hint.textContent = hint || "";
    }
    lvglMockInteractiveElements().forEach((element) => {
        if (element) element.disabled = !lvglMockReady;
    });
}

function postLvglMockMessage(message) {
    const frame = document.getElementById("lvglPreviewFrame");
    if (!frame?.contentWindow || !currentLvglPreviewUrl) return false;
    frame.contentWindow.postMessage(
        { channel: LVGL_MOCK_CHANNEL, ...message },
        window.location.origin
    );
    return true;
}

function resetLvglMockBridge(
    state = "idle",
    hint = "请选择支持 Mock Data 桥接的构建。"
) {
    stopLvglMockProbe();
    setLvglMockAvailability(state, hint);
}

function probeLvglMockBridge() {
    if (lvglMockReady) {
        stopLvglMockProbe();
        return;
    }

    lvglMockProbeAttempts += 1;
    postLvglMockMessage({ action: "probe" });
    if (lvglMockProbeAttempts >= LVGL_MOCK_PROBE_LIMIT) {
        stopLvglMockProbe();
        setLvglMockAvailability(
            "unavailable",
            "该构建未提供 Mock Data 桥接；设备预览与编码器仍可正常使用。"
        );
    }
}

function startLvglMockProbe() {
    resetLvglMockBridge(
        "loading",
        "正在连接预览中的 Mock Data 桥接…"
    );
    probeLvglMockBridge();
    if (!lvglMockReady) {
        lvglMockProbeTimer = setInterval(
            probeLvglMockBridge,
            LVGL_MOCK_PROBE_INTERVAL_MS
        );
    }
}

function syncLvglMockControls(status) {
    const elements = lvglMockElements();
    if (!status?.time || !status?.weather) return;

    if (elements.time) {
        elements.time.value =
            String(status.time.hour).padStart(2, "0") + ":" +
            String(status.time.minute).padStart(2, "0");
    }
    if (elements.timeSynced) {
        elements.timeSynced.checked = Boolean(status.time.synced);
    }
    if (elements.temperature) {
        elements.temperature.value = String(status.weather.temperatureC);
    }
    if (elements.weatherAvailable) {
        elements.weatherAvailable.checked =
            Boolean(status.weather.available);
    }
    if (elements.wifi) elements.wifi.value = status.wifi;
    if (elements.bluetooth) elements.bluetooth.value = status.bluetooth;
}

function lvglMockStatusFromControls() {
    const elements = lvglMockElements();
    const parts = (elements.time?.value || "").split(":");
    const hour = Number(parts[0]);
    const minute = Number(parts[1]);
    const temperatureC = Number(elements.temperature?.value);

    if (
        !Number.isInteger(hour) ||
        hour < 0 ||
        hour > 23 ||
        !Number.isInteger(minute) ||
        minute < 0 ||
        minute > 59
    ) {
        throw new TypeError("请输入有效时间。");
    }
    if (
        !Number.isInteger(temperatureC) ||
        temperatureC < -99 ||
        temperatureC > 99
    ) {
        throw new TypeError("温度必须是 -99 到 99 之间的整数。");
    }

    return {
        time: {
            hour,
            minute,
            synced: Boolean(elements.timeSynced?.checked),
        },
        weather: {
            temperatureC,
            available: Boolean(elements.weatherAvailable?.checked),
        },
        wifi: elements.wifi?.value,
        bluetooth: elements.bluetooth?.value,
    };
}

function sendLvglMockAction(action, detail = {}) {
    if (!lvglMockReady) return false;
    return postLvglMockMessage({ action, ...detail });
}

function reportLvglMockError(error) {
    const hint = document.getElementById("lvglMockHint");
    if (hint) {
        hint.textContent =
            error instanceof Error ? error.message : String(error);
    }
}

function handleLvglMockMessage(event) {
    const frame = document.getElementById("lvglPreviewFrame");
    if (
        event.origin !== window.location.origin ||
        event.source !== frame?.contentWindow ||
        event.data?.channel !== LVGL_MOCK_CHANNEL
    ) {
        return;
    }
    if (
        !lvglPreviewReady &&
        detectLvglPreviewProtocol(frame)
    ) {
        return;
    }

    if (event.data.action === "ready") {
        stopLvglMockProbe();
        setLvglMockAvailability(
            "ready",
            "控制项会在下一次 UI pump 后更新设备状态栏。"
        );
        syncLvglMockControls(event.data.status);
    } else if (event.data.action === "state") {
        syncLvglMockControls(event.data.status);
    } else if (event.data.action === "error") {
        stopLvglMockProbe();
        setLvglMockAvailability(
            "error",
            event.data.message || "Mock Data 操作失败。"
        );
    }
}

function bindLvglMockControls() {
    const elements = lvglMockElements();
    if (!elements.apply) return;

    const presets = [
        [elements.offline, "offline"],
        [elements.connecting, "connecting"],
        [elements.online, "online"],
        [elements.fullyConnected, "fully-connected"],
    ];
    presets.forEach(([button, name]) => {
        button?.addEventListener("click", () => {
            sendLvglMockAction("apply-preset", { name });
        });
    });
    elements.apply.addEventListener("click", () => {
        try {
            sendLvglMockAction("set-status", {
                status: lvglMockStatusFromControls(),
            });
        } catch (error) {
            reportLvglMockError(error);
        }
    });
    elements.reset?.addEventListener("click", () => {
        sendLvglMockAction("reset");
    });
    elements.startDemo?.addEventListener("click", () => {
        sendLvglMockAction("start-demo");
    });
    elements.stopDemo?.addEventListener("click", () => {
        sendLvglMockAction("stop-demo");
    });
    window.addEventListener("message", handleLvglMockMessage);
}

function setLvglPreviewStatus(text, type = "") {
    setStatus("lvglPreviewStatusBox", text, type);
}

function previewJobFromQuery() {
    return new URLSearchParams(window.location.search).get("job_id") || "";
}

function lvglPreviewElements() {
    return {
        card: document.getElementById("lvglPreviewCard"),
        badge: document.getElementById("lvglPreviewLiveBadge"),
        wrap: document.getElementById("lvglPreviewWrap"),
        gateTitle: document.getElementById("lvglPreviewGateTitle"),
        gateMessage: document.getElementById("lvglPreviewGateMessage"),
        retry: document.getElementById("lvglPreviewRetryBtn"),
    };
}

function stopLvglPreviewProbe() {
    if (lvglPreviewProbeTimer) {
        clearInterval(lvglPreviewProbeTimer);
        lvglPreviewProbeTimer = null;
    }
    lvglPreviewProbeAttempts = 0;
}

function setLvglPreviewAvailability(state, title, message) {
    const elements = lvglPreviewElements();
    const labels = {
        idle: "未加载",
        loading: "初始化中",
        ready: "运行中",
        error: "初始化失败",
    };
    lvglPreviewReady = state === "ready";

    if (elements.card) elements.card.dataset.state = state;
    if (elements.badge) {
        elements.badge.textContent = labels[state] || labels.idle;
        elements.badge.className = "tag";
        if (state === "ready") elements.badge.classList.add("success");
        if (state === "error") elements.badge.classList.add("failed");
    }
    elements.wrap?.classList.toggle("loading", state === "loading");
    if (elements.gateTitle) elements.gateTitle.textContent = title || "";
    if (elements.gateMessage) {
        elements.gateMessage.textContent = message || "";
    }
    if (elements.retry) elements.retry.hidden = state !== "error";
}

function resetLvglPreviewBridge() {
    stopLvglPreviewProbe();
    lvglPreviewReady = false;
    lvglPreviewUsesProtocol = false;
}

function postLvglPreviewMessage(message) {
    const frame = document.getElementById("lvglPreviewFrame");
    if (!frame?.contentWindow || !currentLvglPreviewUrl) return false;
    frame.contentWindow.postMessage(
        { channel: LVGL_PREVIEW_CHANNEL, ...message },
        window.location.origin
    );
    return true;
}

function failLvglPreviewInitialization() {
    stopLvglPreviewProbe();
    setLvglPreviewAvailability(
        "error",
        "LVGL 初始化超时",
        "运行时在 60 秒内未就绪，请重新加载预览。"
    );
    resetLvglEncoderBridge(
        "error",
        "预览运行时未完成初始化，无法连接编码器。"
    );
    resetLvglMockBridge(
        "error",
        "预览运行时未完成初始化，无法连接 Mock Data。"
    );
}

function probeLvglPreviewBridge() {
    if (lvglPreviewReady) {
        stopLvglPreviewProbe();
        return;
    }

    lvglPreviewProbeAttempts += 1;
    postLvglPreviewMessage({action: "probe"});
    if (lvglPreviewProbeAttempts >= LVGL_PREVIEW_PROBE_LIMIT) {
        failLvglPreviewInitialization();
    }
}

function startLvglPreviewProbe() {
    stopLvglPreviewProbe();
    setLvglPreviewAvailability(
        "loading",
        "正在初始化 LVGL",
        "正在等待 WebAssembly、SDL 和 UI 运行时就绪…"
    );
    probeLvglPreviewBridge();
    if (!lvglPreviewReady) {
        lvglPreviewProbeTimer = setInterval(
            probeLvglPreviewBridge,
            LVGL_PREVIEW_PROBE_INTERVAL_MS
        );
    }
}

function handleLvglPreviewMessage(event) {
    const frame = document.getElementById("lvglPreviewFrame");
    if (
        event.origin !== window.location.origin ||
        event.source !== frame?.contentWindow ||
        event.data?.channel !== LVGL_PREVIEW_CHANNEL ||
        event.data?.action !== "ready"
    ) {
        return;
    }

    lvglPreviewUsesProtocol = true;
    stopLvglPreviewProbe();
    setLvglPreviewAvailability(
        "ready",
        "",
        ""
    );

    const capabilities = event.data.capabilities || {};
    if (capabilities.encoder === false) {
        resetLvglEncoderBridge(
            "unavailable",
            "该构建未声明编码器能力；鼠标预览仍可使用。"
        );
    } else if (!lvglEncoderReady) {
        startLvglEncoderProbe();
    }

    if (capabilities.mockData === false) {
        resetLvglMockBridge(
            "unavailable",
            "该构建未声明 Mock Data 能力。"
        );
    } else if (!lvglMockReady) {
        startLvglMockProbe();
    }
}

function bindLvglPreviewBridge() {
    document.getElementById("lvglPreviewRetryBtn")?.addEventListener(
        "click",
        reloadLvglPreview
    );
    window.addEventListener("message", handleLvglPreviewMessage);
}

function setLvglPreviewFrameMode(mode) {
    const wrap = document.getElementById("lvglPreviewWrap");
    const workbench = wrap?.closest(".lvgl-workbench");
    const workspaceMode = mode === "workspace";

    wrap?.classList.toggle("workspace-preview", workspaceMode);
    workbench?.classList.toggle("workspace-preview-active", workspaceMode);
}

function detectLvglPreviewProtocol(frame) {
    try {
        const doc = frame.contentDocument || frame.contentWindow?.document;
        return doc?.documentElement?.dataset?.lvglPreviewProtocol === "1";
    } catch (_) {
        return false;
    }
}

function detectLvglPreviewFrameMode(frame) {
    try {
        const doc = frame.contentDocument || frame.contentWindow?.document;
        const declaredMode = doc?.documentElement?.dataset?.lvglPreviewLayout;

        if (declaredMode === "device") return "device";
        if (declaredMode === "workspace") return "workspace";
        if (
            doc?.querySelector(
                '[data-lvgl-preview-layout="workspace"], .simulator-layout, .mock-panel'
            )
        ) {
            return "workspace";
        }
    } catch (_) {
    }
    return "device";
}

function configureLvglPreviewFrame(frame) {
    const mode = detectLvglPreviewFrameMode(frame);

    setLvglPreviewFrameMode(mode);
    if (mode === "device") {
        stripEmscriptenChrome(frame);
    }
    return mode;
}

function setLvglPreview(previewUrl) {
    currentLvglPreviewUrl = previewUrl ? REMOTE_BASE + previewUrl : null;
    const frame = document.getElementById("lvglPreviewFrame");
    const wrap = document.getElementById("lvglPreviewWrap");
    const empty = document.getElementById("lvglPreviewEmpty");

    if (!currentLvglPreviewUrl) {
        resetLvglPreviewBridge();
        resetLvglEncoderBridge();
        resetLvglMockBridge();
        setLvglPreviewAvailability(
            "idle",
            "等待预览",
            "请选择一个成功的 LVGL 构建。"
        );
        setLvglPreviewFrameMode("device");
        setLvglPreviewDimensions();
        frame.removeAttribute("src");
        empty.style.display = "grid";
        return;
    }

    resetLvglPreviewBridge();
    resetLvglEncoderBridge(
        "loading",
        "等待 LVGL 运行时完成初始化…"
    );
    resetLvglMockBridge(
        "loading",
        "等待 LVGL 运行时完成初始化…"
    );
    setLvglPreviewAvailability(
        "loading",
        "正在加载预览",
        "正在载入构建产物和 WebAssembly…"
    );
    setLvglPreviewFrameMode("device");
    empty.style.display = "none";
    frame.src = `${currentLvglPreviewUrl}?t=${Date.now()}`;

    frame.onload = function onPreviewLoad() {
        configureLvglPreviewFrame(frame);
        lvglPreviewUsesProtocol = detectLvglPreviewProtocol(frame);
        if (lvglPreviewUsesProtocol) {
            if (!lvglPreviewReady) startLvglPreviewProbe();
        } else {
            setLvglPreviewAvailability("ready", "", "");
            startLvglEncoderProbe();
            startLvglMockProbe();
        }
        frame.onload = null;
    };
}

function setLvglPreviewDimensions(job) {
    const wrap = document.getElementById("lvglPreviewWrap");
    if (!wrap) return;

    const width = Number.parseInt(job?.width, 10);
    const height = Number.parseInt(job?.height, 10);
    wrap.style.setProperty("--lvgl-preview-width", String(Number.isFinite(width) && width >= 120 ? width : 128));
    wrap.style.setProperty("--lvgl-preview-height", String(Number.isFinite(height) && height >= 120 ? height : 296));
}

function reloadLvglPreview() {
    if (!currentLvglPreviewUrl) {
        setLvglPreviewStatus("请先选择一个成功的构建，再刷新预览。", "failed");
        return;
    }
    setLvglPreview(currentLvglPreviewUrl.replace(REMOTE_BASE, ""));
}

function selectLvglPreviewJob(jobId) {
    const job = lvglPreviewJobs.find((item) => item.id === jobId);
    if (!job || !job.preview_url) return;

    currentJobId = job.id;
    currentJob = job;
    setLvglPreviewDimensions(job);
    setLvglPreview(job.preview_url);
    renderLvglPreviewJobs();

    setText("lvglPreviewJobCard", job.id);
    setText("lvglPreviewSize", lvglJobDimensions(job));
    setLvglPreviewStatus([
        `已选择构建: ${job.id}`,
        `工程: ${job.project_name || "-"}`,
        `尺寸: ${lvglJobDimensions(job)}`,
        `创建时间: ${job.created_at || "-"}`
    ].join("\n"), "success");

    const openLink = document.getElementById("lvglOpenPreviewLink");
    const logLink = document.getElementById("lvglOpenLogLink");
    const downloadLink = document.getElementById("lvglDownloadLink");
    if (openLink) {
        openLink.href = REMOTE_BASE + job.preview_url;
        openLink.classList.remove("disabled");
    }
    if (logLink) {
        logLink.href = job.log_url ? REMOTE_BASE + job.log_url : "#";
        logLink.classList.toggle("disabled", !job.log_url);
    }
    if (downloadLink) {
        const downloadUrl = job.artifact_url || job.download_url;
        downloadLink.href = downloadUrl ? REMOTE_BASE + downloadUrl : "#";
        downloadLink.classList.toggle("disabled", !downloadUrl);
    }
}

function renderLvglPreviewJobs() {
    const list = document.getElementById("lvglPreviewJobsList");
    if (!list) return;

    if (!lvglPreviewJobs.length) {
        currentJobId = null;
        currentJob = null;
        currentLvglPreviewUrl = null;
        setLvglPreview(null);
        list.innerHTML = '<div class="empty-state">暂无成功的 LVGL 预览构建。</div>';
        return;
    }

    list.innerHTML = lvglPreviewJobs.map((job) => {
        const selected = job.id === currentJobId ? " selected" : "";
        const downloadName = job.artifact_name || "lvgl_preview.zip";
        return `
            <button class="list-row${selected}" type="button" onclick="selectLvglPreviewJob('${lvglEscapeHtml(job.id)}')">
                <span>
                    <strong>${lvglEscapeHtml(job.project_name || "-")}</strong>
                    <small>${lvglEscapeHtml(job.id)} · ${lvglEscapeHtml(lvglJobDimensions(job))} · ${lvglEscapeHtml(job.created_at || "")}</small>
                </span>
                <span class="row-meta">
                    <span>${lvglEscapeHtml(downloadName)}</span>
                    <span class="tag success">可预览</span>
                </span>
            </button>
        `;
    }).join("");
}

async function loadLvglPreviewJobs() {
    const list = document.getElementById("lvglPreviewJobsList");
    if (list) list.innerHTML = '<div class="empty-state">正在加载 LVGL 预览构建...</div>';

    try {
        lvglPreviewJobs = (await apiGet("/jobs?kind=lvgl")).filter(isLvglPreviewJob);
        renderLvglPreviewJobs();

        const requestedJobId = previewJobFromQuery();
        const requested = requestedJobId ? lvglPreviewJobs.find((job) => job.id === requestedJobId) : null;
        const defaultJob = requested || lvglPreviewJobs[0];
        if (defaultJob) {
            selectLvglPreviewJob(defaultJob.id);
        }
    } catch (err) {
        if (list) list.innerHTML = `<div class="empty-state failed">加载 LVGL 构建失败：${lvglEscapeHtml(err.message)}</div>`;
        setLvglPreviewStatus(`加载 LVGL 构建失败\n${err.message}`, "failed");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("lvglPreviewJobsList")) return;
    bindLvglPreviewBridge();
    bindLvglEncoderControls();
    bindLvglMockControls();
    resetLvglEncoderBridge();
    resetLvglMockBridge();
    loadLvglPreviewJobs();
});
