"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

function makeClassList() {
    const values = new Set();
    return {
        add: function(name) {
            values.add(name);
        },
        remove: function(name) {
            values.delete(name);
        },
        contains: function(name) {
            return values.has(name);
        }
    };
}

function makeElement(value) {
    return {
        value: value || "",
        checked: false,
        disabled: true,
        textContent: "",
        className: "",
        classList: makeClassList(),
        addEventListener: function() {}
    };
}

const ids = [
    "lvglMockBadge",
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
const posted = [];
const childWindow = {
    postMessage: function(message, origin) {
        posted.push({message, origin});
    }
};
const frame = {contentWindow: childWindow};
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
    stripEmscriptenChrome: function() {}
};

vm.createContext(context);
vm.runInContext(
    fs.readFileSync(process.argv[2], "utf8"),
    context,
    {filename: process.argv[2]}
);

context.setLvglMockAvailability("ready", "ready");
assert.strictEqual(elements.lvglMockBadge.textContent, "Mock 可用");
assert(elements.lvglMockBadge.classList.contains("success"));
assert.strictEqual(elements.lvglMockApplyBtn.disabled, false);

vm.runInContext(
    'currentLvglPreviewUrl = "http://example.test/preview/index.html"',
    context
);
assert.strictEqual(
    context.postLvglMockMessage({
        action: "apply-preset",
        name: "online"
    }),
    true
);
assert.deepStrictEqual(
    JSON.parse(JSON.stringify(posted[0])),
    {
        message: {
            channel: "zlyhub.lvgl.mock.v1",
            action: "apply-preset",
            name: "online"
        },
        origin: "http://example.test"
    }
);

const onlineStatus = {
    time: {hour: 9, minute: 41, synced: true},
    weather: {temperatureC: 26, available: true},
    wifi: "connected",
    bluetooth: "advertising"
};
context.handleLvglMockMessage({
    origin: "http://example.test",
    source: childWindow,
    data: {
        channel: "zlyhub.lvgl.mock.v1",
        action: "state",
        status: onlineStatus
    }
});
assert.strictEqual(elements.lvglMockTime.value, "09:41");
assert.strictEqual(elements.lvglMockTimeSynced.checked, true);
assert.strictEqual(elements.lvglMockTemperature.value, "26");
assert.strictEqual(elements.lvglMockWeatherAvailable.checked, true);
assert.strictEqual(elements.lvglMockWifi.value, "connected");
assert.strictEqual(elements.lvglMockBluetooth.value, "advertising");

context.setLvglMockAvailability("idle", "idle");
context.handleLvglMockMessage({
    origin: "http://wrong-origin.test",
    source: childWindow,
    data: {
        channel: "zlyhub.lvgl.mock.v1",
        action: "ready",
        status: onlineStatus
    }
});
assert.strictEqual(elements.lvglMockApplyBtn.disabled, true);
