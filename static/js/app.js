(function () {
  "use strict";

  var root = document.documentElement;
  var shell = document.querySelector(".app-shell");
  var THEME_KEY = "plantpulse:theme";
  var COLLAPSE_KEY = "plantpulse:sidebar-collapsed";

  // ---------- Theme ----------
  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    var toggle = document.querySelector("[data-theme-toggle]");
    if (toggle) toggle.setAttribute("aria-pressed", theme === "dark");
  }

  function initTheme() {
    var saved = localStorage.getItem(THEME_KEY);
    if (saved) applyTheme(saved);
  }

  function toggleTheme() {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem(THEME_KEY, next);

    // Best-effort sync to the server so the preference follows the user;
    // failures are non-fatal since localStorage already holds the value.
    fetch("/api/theme", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ theme: next }),
    }).catch(function () {});
  }

  function getCsrfToken() {
    var el = document.querySelector('meta[name="csrf-token"]');
    return el ? el.getAttribute("content") : "";
  }

  // ---------- Sidebar collapse (desktop) ----------
  function initSidebarCollapse() {
    var btn = document.querySelector("[data-sidebar-collapse]");
    if (!shell || !btn) return;

    if (localStorage.getItem(COLLAPSE_KEY) === "1") {
      shell.classList.add("is-collapsed");
    }
    btn.addEventListener("click", function () {
      shell.classList.toggle("is-collapsed");
      localStorage.setItem(
        COLLAPSE_KEY,
        shell.classList.contains("is-collapsed") ? "1" : "0"
      );
    });
  }

  // ---------- Mobile drawer ----------
  function initMobileDrawer() {
    var openBtn = document.querySelector("[data-mobile-menu-open]");
    var backdrop = document.querySelector("[data-sidebar-backdrop]");
    if (!shell) return;

    function close() {
      shell.classList.remove("is-mobile-open");
    }
    if (openBtn) {
      openBtn.addEventListener("click", function () {
        shell.classList.add("is-mobile-open");
      });
    }
    if (backdrop) backdrop.addEventListener("click", close);

    document.querySelectorAll(".sidebar-link").forEach(function (link) {
      link.addEventListener("click", close);
    });
  }

  // ---------- Flash message auto-dismiss ----------
  function initFlashDismiss() {
    document.querySelectorAll("[data-flash]").forEach(function (el) {
      setTimeout(function () {
        el.style.transition = "opacity 300ms ease";
        el.style.opacity = "0";
        setTimeout(function () {
          el.remove();
        }, 300);
      }, 6000);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    initSidebarCollapse();
    initMobileDrawer();
    initFlashDismiss();

    var themeBtn = document.querySelector("[data-theme-toggle]");
    if (themeBtn) themeBtn.addEventListener("click", toggleTheme);
  });
})();
