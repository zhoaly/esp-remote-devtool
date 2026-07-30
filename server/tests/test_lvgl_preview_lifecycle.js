"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

function makeClassList() {
    const values = new Set();
    return {
        add: function(name) { values.add(name); },
        remove: function(name) { values.delete(name); },
        toggle: function(name, enabled) {
            if (enabled) values.add(name);
            else values.delete(name);
        },
        contains: function(name) { return values.has(name); }
    };
}

function makeElement() {
    return {
        dataset: {},
        disabled: false,
        hidden: false,
        inert: false,
        textContent: "",
        className: "",
        classList: makeClassList(),
        style: {setProperty: function() {}},
        setAttribute: function(name, value) {
            this[name] = String(value);
        },
        addEventListener: function() {}
    };
}

const ids = [
    "lvglPreviewCard",
    "lvglPreviewLiveBadge",
    "lvglPreviewWrap",
    "lvglPreviewGateTitle",
    "lvglPreviewGateMessage",
    "lvglPreviewRetryBtn",
    "lvglEncoderCard",
    "lvglEncoderBadge",
    "lvglEncoderContent",
    "lvglEncoderStateTitle",
    "lvglEncoderStateMessage",
    "lvglEncoderHint",
    "lvglEncoderLeftBtn",
    "lvglEncoderPressBtn",
    "lvglEncoderRightBtn",
    "lvglMockCard",
    "lvglMockBadge",
    "lvglMockContent",
    "lvglMockStateTitle",
    "lvglMockStateMessage",
    "lvglMockHint",
    "lvglMockTime",
    "lvglMockTimeSynced",
    "lvglMockTemperature",
    "lvglMockWeatherAvailable",
    "lvglMockWifi",
    "lvglMockBluetooth",
    "lvglMockOfflineBtn",
    "lvglMockConnectingBtn",
    "lvglMockOnlineBtn",
    "lvglMockFullyConnectedBtn",
    "lvglMockApplyBtn",
    "lvglMockResetBtn",
    "lvglMockStartDemoBtn",
    "lvglMockStopDemoBtn"
];
const elements = Object.fromEntries(ids.map((id) => [id, makeElement()]));
const workbench = makeElement();
elements.lvglPreviewWrap.closest = function() { return workbench; };

const posted = [];
const childWindow = {
    postMessage: function(message, origin) {
        posted.push({message, origin});
    }
};
const frame = {
    contentWindow: childWindow,
    contentDocument: {
        documentElement: {
            dataset: {
                lvglPreviewLayout: "device",
                lvglPreviewProtocol: "1"
            }
        },
        querySelector: function() { return {}; }
    }
};
let nextInterval = 1;
const context = {
    console,
    URLSearchParams,
    REMOTE_BASE: "http://example.test",
    document: {
        addEventListener: function() {},
        getElementById: function(id) {
            if (id === "lvglPreviewFrame") return frame;
            return elements[id] || null;
        }
    },
    window: {
        location: {search: "", origin: "http://example.test"},
        addEventListener: function() {}
    },
    setInterval: function() { return nextInterval++; },
    clearInterval: function() {},
    stripEmscriptenChrome: function() {}
};

vm.createContext(context);
vm.runInContext(
    fs.readFileSync(process.argv[2], "utf8"),
    context,
    {filename: process.argv[2]}
);
vm.runInContext(
    'currentLvglPreviewUrl = "http://example.test/preview/index.html"',
    context
);

assert.strictEqual(context.detectLvglPreviewProtocol(frame), true);
context.setLvglPreviewAvailability(
    "loading",
    "正在初始化 LVGL",
    "waiting"
);
assert.strictEqual(elements.lvglPreviewCard.dataset.state, "loading");
assert.strictEqual(elements.lvglPreviewLiveBadge.textContent, "初始化中");
assert(elements.lvglPreviewWrap.classList.contains("loading"));

context.handleLvglPreviewMessage({
    origin: "http://example.test",
    source: childWindow,
    data: {
        channel: "zlyhub.lvgl.preview.v1",
        action: "ready",
        capabilities: {
            encoder: false,
            mockData: false
        }
    }
});
assert.strictEqual(elements.lvglPreviewCard.dataset.state, "ready");
assert.strictEqual(elements.lvglPreviewLiveBadge.textContent, "运行中");
assert.strictEqual(elements.lvglEncoderCard.dataset.state, "unavailable");
assert.strictEqual(elements.lvglMockCard.dataset.state, "unavailable");

context.resetLvglEncoderBridge("loading", "waiting");
for (let index = 0; index < 41; index += 1) {
    context.probeLvglEncoderBridge();
}
assert.strictEqual(elements.lvglEncoderCard.dataset.state, "loading");
for (let index = 41; index < 240; index += 1) {
    context.probeLvglEncoderBridge();
}
assert.strictEqual(elements.lvglEncoderCard.dataset.state, "unavailable");

context.setLvglPreviewAvailability("loading", "loading", "loading");
context.handleLvglPreviewMessage({
    origin: "http://wrong-origin.test",
    source: childWindow,
    data: {
        channel: "zlyhub.lvgl.preview.v1",
        action: "ready",
        capabilities: {}
    }
});
assert.strictEqual(elements.lvglPreviewCard.dataset.state, "loading");

context.failLvglPreviewInitialization();
assert.strictEqual(elements.lvglPreviewCard.dataset.state, "error");
assert.strictEqual(elements.lvglPreviewRetryBtn.hidden, false);
assert.strictEqual(elements.lvglEncoderCard.dataset.state, "error");
assert.strictEqual(elements.lvglMockCard.dataset.state, "error");
