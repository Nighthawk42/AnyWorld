"use strict";

(function () {
    const THEME_STORAGE_KEY = "anyworld_theme";
    const VALID_THEMES = new Set([
        "default",
        "catppuccin-mocha",
        "catppuccin-latte",
        "github-dark",
        "github-light",
    ]);

    function getSavedTheme() {
        try {
            const saved = localStorage.getItem(THEME_STORAGE_KEY);
            if (saved && VALID_THEMES.has(saved)) {
                return saved;
            }
        } catch {
            // localStorage unavailable
        }
        return "default";
    }

    function applyTheme(theme) {
        if (!VALID_THEMES.has(theme)) theme = "default";
        document.documentElement.dataset.theme = theme;
        try {
            localStorage.setItem(THEME_STORAGE_KEY, theme);
        } catch {
            // localStorage unavailable
        }

        document.querySelectorAll(".theme-select").forEach((select) => {
            select.value = theme;
        });
    }

    // Apply immediately to prevent theme flash
    applyTheme(getSavedTheme());

    function initThemeControls() {
        const current = getSavedTheme();
        document.querySelectorAll(".theme-select").forEach((select) => {
            select.value = current;
            select.addEventListener("change", (e) => {
                applyTheme(e.target.value);
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initThemeControls);
    } else {
        initThemeControls();
    }

    window.applyTheme = applyTheme;
    window.getSavedTheme = getSavedTheme;
})();
