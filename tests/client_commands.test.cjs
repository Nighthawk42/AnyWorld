const assert = require("node:assert/strict");
const { test } = require("node:test");
const { readFileSync } = require("node:fs");
const { randomUUID, createHash, webcrypto } = require("node:crypto");
const vm = require("node:vm");
const path = require("node:path");

const source = ["state", "identity", "rendering", "transport", "accessibility", "journal", "audio", "commands", "app"]
    .map((name) => readFileSync(path.join(__dirname, `../static/js/${name}.js`), "utf8"))
    .join("\n");

function storage() {
    const values = new Map();
    return {
        getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => values.set(key, value),
    };
}

function browser(localStorage = storage(), sessionStorage = storage()) {
    const nodes = new Map();
    function node(id) {
        if (!nodes.has(id)) nodes.set(id, {
            id, hidden: false, disabled: false, value: "", textContent: "",
            dataset: {}, style: {}, children: [], listeners: {},
            classList: { add() {}, remove() {} },
            addEventListener(type, callback) { this.listeners[type] = callback; },
            querySelector() { return node("button"); },
            querySelectorAll() { return []; },
            append(...items) { this.children.push(...items); },
            appendChild(item) { this.children.push(item); },
            replaceChildren(...items) { this.children = [...items]; },
            focus() {}, after() {}, click() {}, setAttribute() {},
            getClientRects() { return [1]; }, contains() { return false; },
        });
        return nodes.get(id);
    }
    const sockets = [];
    class Socket {
        static CONNECTING = 0; static OPEN = 1; static CLOSING = 2;
        constructor(url) {
            this.url = url; this.readyState = 0; this.listeners = {}; this.sent = [];
            sockets.push(this);
        }
        addEventListener(type, callback) { this.listeners[type] = callback; }
        open() { this.readyState = 1; this.listeners.open(); }
        send(data) { this.sent.push(JSON.parse(data)); }
        close(code = 1006) { this.readyState = 3; this.listeners.close?.({ code }); }
        receive(type, payload) { this.listeners.message({ data: JSON.stringify({ type, payload }) }); }
    }
    const timers = new Map();
    let timerId = 0;
    const setTimeout = (callback, delay) => {
        timers.set(++timerId, { callback, delay });
        return timerId;
    };
    const clearTimeout = (id) => timers.delete(id);
    const window = {
        location: { protocol: "https:", host: "game.test:4141" },
        crypto: { randomUUID, subtle: webcrypto.subtle, getRandomValues: (arr) => webcrypto.getRandomValues(arr) },
        localStorage, sessionStorage, setTimeout,
        applyTheme(theme) { window.currentTheme = theme; },
        getSavedTheme() { return window.currentTheme || "default"; },
    };
    const runtime = {
        window, sessionStorage, WebSocket: Socket, setTimeout, clearTimeout, console, Blob, TextEncoder,
        URL: { createObjectURL() { return "blob:test"; }, revokeObjectURL() {} },
        MutationObserver: class { observe() {} },
        document: { getElementById: node, createElement: node, listeners: {},
            createDocumentFragment: () => node("fragment"),
            addEventListener(type, callback) { this.listeners[type] = callback; } },
    };
    vm.runInNewContext(source, runtime);
    return {
        runtime, session: vm.runInNewContext("clientSession", runtime),
        sockets, node,
        async login(name = "Arxs") {
            node("name-input").value = name;
            node("password-input").value = "party-password";
            await node("login-form").listeners.submit({ preventDefault() {} });
            sockets.at(-1).receive("auth_ok", {
                name, reconnect_token: "tok", is_host: false, state: "ACTIVE_TURN",
                players: [], player_order: [],
            });
        },
    };
}

test("slash commands handle /help, /clear, /theme, /tts, /roll, /me, /ooc, /remember", async () => {
    const tab = await browser();
    tab.sockets[0].open();
    await tab.login("Arxs");
    const socket = tab.sockets[0];
    const chatInput = tab.node("chat-input");
    const chatForm = tab.node("chat-form");
    const chatMessages = tab.node("chat-messages");

    // 1. /help
    chatInput.value = "/help";
    chatForm.listeners.submit({ preventDefault() {} });
    assert.equal(chatInput.value, "");
    assert.ok(chatMessages.children.some((c) => (c.textContent || "").includes("Slash Commands")));

    // 2. /roll 2d6+3
    const sentCountBeforeRoll = socket.sent.length;
    chatInput.value = "/roll 2d6+3";
    chatForm.listeners.submit({ preventDefault() {} });
    assert.equal(chatInput.value, "");
    assert.equal(socket.sent.length, sentCountBeforeRoll + 1);
    const rollMsg = socket.sent.at(-1);
    assert.equal(rollMsg.event_type, "chat");
    assert.match(rollMsg.data.message, /🎲 \*\*Arxs\*\* rolled `2d6 \+ 3`/);

    // 3. /me draws sword
    chatInput.value = "/me draws sword";
    chatForm.listeners.submit({ preventDefault() {} });
    const meMsg = socket.sent.at(-1);
    assert.equal(meMsg.data.message, "*Arxs draws sword*");

    // 4. /ooc brb
    chatInput.value = "/ooc brb";
    chatForm.listeners.submit({ preventDefault() {} });
    const oocMsg = socket.sent.at(-1);
    assert.equal(oocMsg.data.message, "**[OOC]** brb");

    // 5. /remember The chest has a trap
    chatInput.value = "/remember The chest has a trap";
    chatForm.listeners.submit({ preventDefault() {} });
    const remMsg = socket.sent.at(-1);
    assert.equal(remMsg.event_type, "remember");
    assert.equal(remMsg.data.fact, "The chest has a trap");

    // 6. /tts on and /tts off
    chatInput.value = "/tts on";
    chatForm.listeners.submit({ preventDefault() {} });
    assert.equal(tab.runtime.window.isTTSAuto(), true);

    chatInput.value = "/tts off";
    chatForm.listeners.submit({ preventDefault() {} });
    assert.equal(tab.runtime.window.isTTSAuto(), false);

    // 7. /theme catppuccin-mocha
    chatInput.value = "/theme catppuccin-mocha";
    chatForm.listeners.submit({ preventDefault() {} });
    assert.equal(tab.runtime.window.currentTheme, "catppuccin-mocha");

    // 8. /clear
    chatInput.value = "/clear";
    chatForm.listeners.submit({ preventDefault() {} });
    // chat-messages cleared then replaced with confirmation
    assert.ok(chatMessages.children.length > 0);
    assert.ok(chatMessages.children.at(-1).textContent.includes("Chat cleared"));
});
