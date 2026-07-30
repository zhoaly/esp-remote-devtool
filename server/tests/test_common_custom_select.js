"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

function makeClassList(owner) {
    const values = new Set();
    return {
        add: function() {
            Array.from(arguments).forEach((name) => values.add(name));
        },
        remove: function(name) { values.delete(name); },
        toggle: function(name, enabled) {
            if (enabled) values.add(name);
            else values.delete(name);
        },
        contains: function(name) { return values.has(name); },
        setFromString: function(value) {
            values.clear();
            String(value).split(/\s+/).filter(Boolean).forEach(
                (name) => values.add(name)
            );
            owner._className = String(value);
        }
    };
}

function FakeElement(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.disabled = false;
    this.textContent = "";
    this.classList = makeClassList(this);
}
Object.defineProperty(FakeElement.prototype, "className", {
    get: function() { return this._className || ""; },
    set: function(value) { this.classList.setFromString(value); }
});
FakeElement.prototype.append = function() {
    Array.from(arguments).forEach((child) => this.children.push(child));
};
FakeElement.prototype.appendChild = function(child) {
    this.children.push(child);
};
FakeElement.prototype.addEventListener = function() {};
FakeElement.prototype.setAttribute = function(name, value) {
    this.attributes[name] = String(value);
};
FakeElement.prototype.querySelector = function(selector) {
    const className = selector.startsWith(".") ? selector.slice(1) : "";
    const queue = this.children.slice();
    while (queue.length) {
        const child = queue.shift();
        if (child.classList?.contains(className)) return child;
        queue.push.apply(queue, child.children || []);
    }
    return null;
};
FakeElement.prototype.closest = function() { return null; };

const select = new FakeElement("select");
select.disabled = true;
select.options = [
    {textContent: "Disconnected", value: "disconnected", selected: true},
    {textContent: "Connected", value: "connected", selected: false}
];
select.selectedIndex = 0;
select.addEventListener = function() {};
select.insertAdjacentElement = function(_position, element) {
    this.nextElementSibling = element;
};

const context = {
    console,
    window: {
        location: {origin: "http://example.test"},
        localStorage: {
            getItem: function() { return null; },
            setItem: function() {},
            removeItem: function() {}
        }
    },
    document: {
        addEventListener: function() {},
        querySelectorAll: function() { return []; },
        createElement: function(tagName) {
            return new FakeElement(tagName);
        }
    },
    MutationObserver: function() {
        this.observe = function() {};
    },
    Event: function(type) { this.type = type; },
    Element: FakeElement
};

vm.createContext(context);
vm.runInContext(
    fs.readFileSync(process.argv[2], "utf8"),
    context,
    {filename: process.argv[2]}
);

context.enhanceSelect(select);
const custom = select.nextElementSibling;
const trigger = custom.querySelector(".custom-select-trigger");
assert(select.classList.contains("native-select-hidden"));
assert(custom.classList.contains("disabled"));
assert.strictEqual(trigger.disabled, true);
assert.strictEqual(trigger.attributes["aria-disabled"], "true");

select.disabled = false;
select.selectedIndex = 1;
select.options[0].selected = false;
select.options[1].selected = true;
context.refreshCustomSelect(select);
assert(!custom.classList.contains("disabled"));
assert.strictEqual(trigger.disabled, false);
assert.strictEqual(
    custom.querySelector(".custom-select-value").textContent,
    "Connected"
);

const css = fs.readFileSync(process.argv[3], "utf8");
assert(css.includes(".lvgl-mock-card select.native-select-hidden:disabled"));
assert(css.includes(":disabled:not(.native-select-hidden)"));
