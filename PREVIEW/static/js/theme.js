(function () {
  var STORAGE_KEY = "v2c-theme";
  var root = document.documentElement;
  var btn = document.getElementById("v2c-theme-toggle");
  var icon = document.getElementById("v2c-theme-icon");

  function applyIcon(theme) {
    if (!icon) return;
    icon.textContent = theme === "dark" ? "☽" : "☀";
  }

  applyIcon(root.getAttribute("data-theme") || "dark");

  if (!btn) return;
  btn.addEventListener("click", function () {
    var current = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
    var next = current === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    applyIcon(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (e) {}
  });
})();

(function () {
  var toggle = document.getElementById("v2c-sidebar-toggle");
  var sidebar = document.getElementById("v2c-sidebar");
  var backdrop = document.getElementById("v2c-sidebar-backdrop");
  if (!toggle || !sidebar || !backdrop) return;

  function setOpen(open) {
    sidebar.classList.toggle("is-open", open);
    backdrop.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  toggle.addEventListener("click", function () {
    setOpen(!sidebar.classList.contains("is-open"));
  });
  backdrop.addEventListener("click", function () { setOpen(false); });
})();
