function setViewportHeight() {
    document.documentElement.style.setProperty("--vh", window.innerHeight * 0.01 + "px");
}
setViewportHeight();
window.addEventListener("resize", setViewportHeight);

const toast = document.getElementById("toast");
const drawer = document.getElementById("personDrawer");
const bottomNav = document.getElementById("bottomNav");
const sheet = document.getElementById("global-sheet");
const sheetOverlay = document.getElementById("sheet-overlay");

function scrollToSection(id) {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(window.toastTimer);
    window.toastTimer = setTimeout(() => toast.classList.remove("show"), 1700);
}

function toggleGeneration(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const wasHidden = el.classList.contains("hidden");
    el.classList.toggle("hidden");
    el.classList.add("revealed");
    showToast(wasHidden ? "Descendants revealed" : "Branch collapsed");
}

function revealAll() {
    document.querySelectorAll(".generation.hidden").forEach((el) => {
        el.classList.remove("hidden");
        el.classList.add("revealed");
    });
    showToast("Full branch revealed");
}

function selectPerson(event, name, meta, avatar) {
    document.querySelectorAll(".person-card").forEach((card) => card.classList.remove("selected"));
    event.currentTarget.classList.add("selected");

    const drawerName = document.getElementById("drawerName");
    const drawerMeta = document.getElementById("drawerMeta");
    const drawerAvatar = document.getElementById("drawerAvatar");
    if (drawerName) drawerName.textContent = name;
    if (drawerMeta) drawerMeta.textContent = meta;
    if (drawerAvatar) drawerAvatar.textContent = avatar;

    if (drawer) drawer.classList.add("show");
}

function closeDrawer() {
    if (drawer) drawer.classList.remove("show");
}

function closeSheet() {
    if (sheet) {
        sheet.classList.remove("show");
        sheet.innerHTML = "";
    }
    if (sheetOverlay) sheetOverlay.classList.remove("show");
}

// Keyboard hides bottom nav
if (bottomNav) {
    document.addEventListener("focusin", (e) => {
        if (
            e.target.tagName === "INPUT" ||
            e.target.tagName === "TEXTAREA" ||
            e.target.tagName === "SELECT" ||
            e.target.isContentEditable
        ) {
            bottomNav.classList.add("hidden-for-keyboard");
        }
    });

    document.addEventListener("focusout", () => {
        bottomNav.classList.remove("hidden-for-keyboard");
    });
}

// HTMX hooks
document.body.addEventListener("showToast", (event) => {
    showToast(event.detail.value);
});

document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target.id === "personDrawer") {
        event.detail.target.classList.add("show");
    }
    if (event.detail.target.id === "global-sheet") {
        event.detail.target.classList.add("show");
        if (sheetOverlay) sheetOverlay.classList.add("show");
    }
});

// Active bottom nav item per page
document.addEventListener("DOMContentLoaded", () => {
    const path = window.location.pathname;
    const navLinks = document.querySelectorAll(".bottom-nav a");
    navLinks.forEach((link) => {
        link.classList.remove("active");
        if (link.getAttribute("href") === path) {
            link.classList.add("active");
        }
    });

    // Mark current page in desktop sidebar
    const sideLinks = document.querySelectorAll(".side-link");
    sideLinks.forEach((link) => {
        link.classList.remove("active");
        const href = link.getAttribute("href");
        if (href && path.startsWith(href) && href !== "/") {
            link.classList.add("active");
        } else if (href === "/" && path === "/") {
            link.classList.add("active");
        }
    });
});

document.addEventListener("click", (event) => {
    const treeSheet = document.getElementById("tree-create-sheet");
    if (!treeSheet && event.target.closest("[data-create-sheet-trigger]")) {
        showToast("Create menu is available from the tree homepage");
    }

    if (!treeSheet && event.target.closest("[data-tree-search-trigger]")) {
        showToast("Search is available from the tree homepage");
    }
});
