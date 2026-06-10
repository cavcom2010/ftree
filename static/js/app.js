document.addEventListener("DOMContentLoaded", function () {
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach(function (item) {
        item.addEventListener("click", function (e) {
            if (item.classList.contains("nav-add")) return;
            navItems.forEach(function (el) { el.classList.remove("active"); });
            item.classList.add("active");
        });
    });
});
