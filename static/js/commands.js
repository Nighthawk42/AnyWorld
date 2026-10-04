"use strict";

const THEMES = [
    "default",
    "catppuccin-mocha",
    "catppuccin-latte",
    "github-dark",
    "github-light",
];

/**
 * Parses a dice expression: e.g. "1d20+5", "2d6", "d%", "d100", "3d8-2".
 * Returns { count, sides, modifier, sign, modValue } or null if invalid.
 */
function parseDiceExpression(str) {
    if (!str) return null;
    const clean = str.trim().toLowerCase();
    const match = clean.match(/^(\d*)d(\d+|%)(?:([+-])(\d+))?$/);
    if (!match) return null;

    const count = match[1] === "" ? 1 : parseInt(match[1], 10);
    const sides = match[2] === "%" ? 100 : parseInt(match[2], 10);
    const sign = match[3];
    const modValue = match[4] ? parseInt(match[4], 10) : 0;
    const modifier = sign === "-" ? -modValue : modValue;

    if (count < 1 || count > 100 || sides < 2 || sides > 10000 || Math.abs(modifier) > 10000) {
        return null;
    }

    return { count, sides, modifier, sign: sign || "+", modValue };
}

/**
 * Rolls random dice using window.crypto for quality entropy.
 */
function rollDice(count, sides) {
    const array = new Uint32Array(count);
    window.crypto.getRandomValues(array);
    const rolls = [];
    for (let i = 0; i < count; i++) {
        rolls.push((array[i] % sides) + 1);
    }
    return rolls;
}

/**
 * Handle slash commands from chat input or action input.
 * Returns true if the message was handled as a slash command, false otherwise.
 */
function handleSlashCommand(rawText, sourceInput = "chat") {
    const text = rawText.trim();
    if (!text.startsWith("/")) {
        return false;
    }

    const spaceIdx = text.indexOf(" ");
    const command = (spaceIdx === -1 ? text.slice(1) : text.slice(1, spaceIdx)).toLowerCase();
    const args = spaceIdx === -1 ? "" : text.slice(spaceIdx + 1).trim();

    const playerName = clientSession.savedAuth?.name || "Player";

    switch (command) {
        case "help": {
            const helpText = [
                "### Anyworld Slash Commands",
                "- **/roll <dice>**: Roll dice (e.g. `/roll 1d20+5`, `/roll 2d6`, `/roll d%`, `/roll 3d8-1`)",
                "- **/me <action>**: Send an in-character action/emote (e.g. `/me draws a gleaming rapier`)",
                "- **/ooc <message>**: Send an out-of-character chat message (e.g. `/ooc Be right back, grabbing water`)",
                "- **/remember <fact>**: Permanently pin a world/character fact into the DM's durable memory",
                "- **/clear**: Clear the current chat display in this window",
                "- **/tts [on|off]**: Toggle or check automatic audio narration of game rounds",
                "- **/theme [name]**: Switch theme (`default`, `catppuccin-mocha`, `catppuccin-latte`, `github-dark`, `github-light`)",
                "- **/help**: Show this help manual",
            ].join("\n");
            appendChat(elements.chatMessages, "Help", helpText, "chat-entry system-chat");
            return true;
        }

        case "clear": {
            elements.chatMessages.replaceChildren();
            appendChat(elements.chatMessages, "System", "Chat cleared.", "chat-entry system-chat");
            return true;
        }

        case "theme": {
            if (!args) {
                const current = window.getSavedTheme ? window.getSavedTheme() : "default";
                appendChat(
                    elements.chatMessages,
                    "System",
                    `Current theme: **${current}**\n\nAvailable themes: ${THEMES.map((t) => `\`${t}\``).join(", ")}\n\nUsage: \`/theme <name>\``,
                    "chat-entry system-chat"
                );
                return true;
            }
            const theme = args.toLowerCase();
            if (THEMES.includes(theme)) {
                if (window.applyTheme) {
                    window.applyTheme(theme);
                }
                appendChat(elements.chatMessages, "System", `Theme changed to **${theme}**.`, "chat-entry system-chat");
            } else {
                appendChat(
                    elements.chatMessages,
                    "System",
                    `Unknown theme: \`${args}\`. Available: ${THEMES.map((t) => `\`${t}\``).join(", ")}`,
                    "chat-entry system-chat error"
                );
            }
            return true;
        }

        case "tts": {
            const sub = args.toLowerCase();
            if (["on", "enable", "true", "1"].includes(sub)) {
                if (window.setTTSAuto) window.setTTSAuto(true);
                appendChat(elements.chatMessages, "System", "TTS auto-narration is now **ON**.", "chat-entry system-chat");
            } else if (["off", "disable", "false", "0"].includes(sub)) {
                if (window.setTTSAuto) window.setTTSAuto(false);
                appendChat(elements.chatMessages, "System", "TTS auto-narration is now **OFF**.", "chat-entry system-chat");
            } else {
                const current = window.isTTSAuto && window.isTTSAuto() ? "ON" : "OFF";
                appendChat(
                    elements.chatMessages,
                    "System",
                    `TTS auto-narration is currently **${current}**.\n\nUsage: \`/tts on\` or \`/tts off\``,
                    "chat-entry system-chat"
                );
            }
            return true;
        }

        case "roll": {
            if (!args) {
                appendChat(elements.chatMessages, "System", "Usage: `/roll <expression>` (e.g. `/roll 1d20+5`, `/roll 2d6`, `/roll d%`)", "chat-entry system-chat error");
                return true;
            }
            const parsed = parseDiceExpression(args);
            if (!parsed) {
                appendChat(elements.chatMessages, "System", `Invalid dice expression: \`${args}\`. Example: \`/roll 1d20+5\`, \`/roll 2d6\`, \`/roll d%\``, "chat-entry system-chat error");
                return true;
            }
            const rolls = rollDice(parsed.count, parsed.sides);
            const sum = rolls.reduce((acc, v) => acc + v, 0);
            const total = sum + parsed.modifier;
            const diceName = `${parsed.count}d${parsed.sides === 100 && args.includes("%") ? "%" : parsed.sides}`;
            const modDisplay = parsed.modifier !== 0 ? ` ${parsed.sign} ${parsed.modValue}` : "";
            const rollsDisplay = rolls.length > 1 || parsed.modifier !== 0 ? ` [${rolls.join(", ")}]${modDisplay} =` : "";
            const message = `🎲 **${playerName}** rolled \`${diceName}${modDisplay}\`:${rollsDisplay} **${total}**`;
            send("chat", { message });
            return true;
        }

        case "me": {
            if (!args) {
                appendChat(elements.chatMessages, "System", "Usage: `/me <action>` (e.g. `/me inspects the runes`)", "chat-entry system-chat error");
                return true;
            }
            const message = `*${playerName} ${args}*`;
            send("chat", { message });
            return true;
        }

        case "ooc": {
            if (!args) {
                appendChat(elements.chatMessages, "System", "Usage: `/ooc <message>` (e.g. `/ooc grabbing a snack`)", "chat-entry system-chat error");
                return true;
            }
            const message = `**[OOC]** ${args}`;
            send("chat", { message });
            return true;
        }

        case "remember": {
            if (!args) {
                appendChat(elements.chatMessages, "System", "Usage: `/remember <important fact to pin in DM memory>`", "chat-entry system-chat error");
                return true;
            }
            send("remember", { fact: args });
            return true;
        }

        default: {
            appendChat(
                elements.chatMessages,
                "System",
                `Unknown command: \`/${command}\`. Type \`/help\` for a list of available commands.`,
                "chat-entry system-chat error"
            );
            return true;
        }
    }
}

window.handleSlashCommand = handleSlashCommand;
window.parseDiceExpression = parseDiceExpression;
window.rollDice = rollDice;
