function setViewportHeight() {
  document.documentElement.style.setProperty("--vh", window.innerHeight * 0.01 + "px");
}
setViewportHeight();
window.addEventListener("resize", setViewportHeight);

const drawer = document.getElementById("personDrawer");
const bottomNav = document.getElementById("bottomNav");
const sheet = document.getElementById("global-sheet");
const sheetOverlay = document.getElementById("sheet-overlay");
const detailSheet = document.getElementById("detailSheet");
const detailSheetOverlay = document.getElementById("detailSheetOverlay");
const accountSheet = document.getElementById("accountSheet");
const accountSheetBackdrop = document.getElementById("accountSheetBackdrop");
let activeAccountTrigger = null;
let accountSheetTimer = null;

function scrollToSection(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function getToastStack() {
  let toastStack = document.querySelector(".app-toast-stack");
  if (!toastStack) {
    toastStack = document.createElement("div");
    toastStack.className = "app-toast-stack";
    toastStack.setAttribute("aria-live", "polite");
    toastStack.setAttribute("aria-atomic", "true");
    document.body.appendChild(toastStack);
  }
  return toastStack;
}

function removeToast(toastElement) {
  if (!toastElement || toastElement.classList.contains("is-leaving")) return;
  toastElement.classList.add("is-leaving");
  window.setTimeout(() => toastElement.remove(), 180);
}

function bindToast(toastElement) {
  if (!toastElement || toastElement.dataset.boundToast === "true") return;
  toastElement.dataset.boundToast = "true";

  const closeButton = toastElement.querySelector(".app-toast-close");
  if (closeButton) {
    closeButton.addEventListener("click", () => removeToast(toastElement));
  }

  window.setTimeout(() => removeToast(toastElement), 2800);
}

function showToast(message, type = "success") {
  if (!message) return;
  const allowedTypes = ["success", "warning", "error"];
  const toastType = allowedTypes.includes(type) ? type : "success";
  const toastStack = getToastStack();
  const toastElement = document.createElement("div");
  toastElement.className = `app-toast app-toast-${toastType}`;
  toastElement.setAttribute("data-toast", "");
  toastElement.innerHTML = `
    <span class="app-toast-dot" aria-hidden="true"></span>
    <span class="app-toast-text"></span>
    <button class="app-toast-close" type="button" aria-label="Dismiss notification">&times;</button>
  `;
  const toastText = toastElement.querySelector(".app-toast-text");
  if (toastText) toastText.textContent = message;

  toastStack.appendChild(toastElement);
  bindToast(toastElement);
}

window.showToast = showToast;

function toggleGeneration(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle("hidden");
  el.classList.add("revealed");
}

function revealAll() {
  document.querySelectorAll(".generation.hidden").forEach((el) => {
    el.classList.remove("hidden");
    el.classList.add("revealed");
  });
}

function selectPerson(event, name, meta, avatar) {
  document.querySelectorAll(".person-card-legacy").forEach((card) => card.classList.remove("selected"));
  if (event && event.currentTarget) {
    event.currentTarget.classList.add("selected");
  }

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
  if (detailSheet) detailSheet.classList.remove("show");
  if (detailSheetOverlay) detailSheetOverlay.classList.remove("show");
}

function setAccountTriggersExpanded(isExpanded) {
  document.querySelectorAll("[data-account-sheet-trigger]").forEach((trigger) => {
    trigger.setAttribute("aria-expanded", isExpanded ? "true" : "false");
  });
}

function openAccountSheet(trigger) {
  if (!accountSheet || !accountSheetBackdrop) return false;

  activeAccountTrigger = trigger || null;
  window.clearTimeout(accountSheetTimer);
  accountSheet.hidden = false;
  accountSheetBackdrop.hidden = false;
  accountSheet.setAttribute("aria-hidden", "false");
  document.body.classList.add("account-sheet-open");
  setAccountTriggersExpanded(true);

  window.requestAnimationFrame(() => {
    accountSheet.classList.add("show");
    accountSheetBackdrop.classList.add("show");
  });

  window.setTimeout(() => {
    const closeButton = accountSheet.querySelector("[data-account-sheet-close]");
    if (closeButton) closeButton.focus({ preventScroll: true });
  }, 80);

  return true;
}

function closeAccountSheet(restoreFocus = true) {
  if (!accountSheet || !accountSheetBackdrop || accountSheet.hidden) return;

  accountSheet.classList.remove("show");
  accountSheetBackdrop.classList.remove("show");
  accountSheet.setAttribute("aria-hidden", "true");
  document.body.classList.remove("account-sheet-open");
  setAccountTriggersExpanded(false);

  window.clearTimeout(accountSheetTimer);
  accountSheetTimer = window.setTimeout(() => {
    accountSheet.hidden = true;
    accountSheetBackdrop.hidden = true;
  }, 260);

  if (restoreFocus && activeAccountTrigger && typeof activeAccountTrigger.focus === "function") {
    activeAccountTrigger.focus({ preventScroll: true });
  }
  activeAccountTrigger = null;
}

function openSheet(name, meta, initials, gradient, born, location, gen, children, relation) {
  const sheetAvatar = document.getElementById("sheetAvatar");
  const sheetName = document.getElementById("sheetName");
  const sheetMeta = document.getElementById("sheetMeta");
  const sheetBorn = document.getElementById("sheetBorn");
  const sheetLocation = document.getElementById("sheetLocation");
  const sheetGen = document.getElementById("sheetGen");
  const sheetChildren = document.getElementById("sheetChildren");
  const sheetRelation = document.getElementById("sheetRelation");

  if (sheetAvatar) {
    sheetAvatar.textContent = initials;
    sheetAvatar.style.background = gradient;
  }
  if (sheetName) sheetName.textContent = name;
  if (sheetMeta) sheetMeta.textContent = meta;
  if (sheetBorn) sheetBorn.textContent = born;
  if (sheetLocation) sheetLocation.textContent = location;
  if (sheetGen) sheetGen.textContent = gen;
  if (sheetChildren) sheetChildren.textContent = children;
  if (sheetRelation) sheetRelation.textContent = relation;

  if (detailSheetOverlay) detailSheetOverlay.classList.add("show");
  if (detailSheet) detailSheet.classList.add("show");
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
if (document.body) {
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
}

// Active bottom nav item per page
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-toast]").forEach(bindToast);

  const path = window.location.pathname;
  const navLinks = document.querySelectorAll(".bottom-nav a");
  navLinks.forEach((link) => {
    link.classList.remove("active");
    const matches = (link.dataset.navMatch || "").split(/\s+/).filter(Boolean);
    if (link.getAttribute("href") === path || matches.includes(path)) {
      link.classList.add("active");
    }
  });

  // Mark current page in desktop sidebar
  const sideLinks = document.querySelectorAll(".side-link");
  sideLinks.forEach((link) => {
    link.classList.remove("active");
    const href = link.getAttribute("href");
    const matches = (link.dataset.navMatch || "").split(/\s+/).filter(Boolean);
    if (matches.includes(path)) {
      link.classList.add("active");
    } else if (href && path.startsWith(href) && href !== "/") {
      link.classList.add("active");
    } else if (href === "/" && path === "/") {
      link.classList.add("active");
    }
  });

  // Initialize Lucide icons
  if (typeof lucide !== "undefined") {
    lucide.createIcons();
  }
});

document.addEventListener("click", (event) => {
  const accountTrigger = event.target.closest("[data-account-sheet-trigger]");
  if (accountTrigger && openAccountSheet(accountTrigger)) {
    event.preventDefault();
    return;
  }

  if (event.target.closest("[data-account-sheet-close]")) {
    closeAccountSheet();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeAccountSheet();
  }
});

// Scroll animations are handled by CSS animate-in class.
// The fadeUp animation plays when elements are painted, ensuring content
// is visible even if JavaScript loads after the initial render.
