(function () {
  function setTheme(theme) {
    document.body.setAttribute("data-theme", theme);
    window.localStorage.setItem("hopki-docs-theme", theme);
    var button = document.querySelector(".hopki-theme-toggle");
    if (button) {
      button.textContent = theme === "dark" ? "light theme" : "dark theme";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var saved = window.localStorage.getItem("hopki-docs-theme") || "dark";
    setTheme(saved);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "hopki-theme-toggle";
    button.addEventListener("click", function () {
      setTheme(document.body.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });
    document.body.appendChild(button);
    setTheme(saved);
  });
})();
