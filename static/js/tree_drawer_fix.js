(function () {
  "use strict";

  var activeTrigger = null;
  var touchStart = null;

  function isTreePage() {
    return !!document.querySelector("[data-tree-page]");
  }

  function closestRevealTrigger(target) {
    if (!target || typeof target.closest !== "function") return null;
    return target.closest("[data-person-reveal]");
  }

  function setBodyLock() {
    var hasOpenDrawer = !!document.querySelector(".tree-reveal-drawer.is-open");
    var hasOpenCreateSheet = !!document.querySelector("#tree-create-sheet.is-open");
    document.body.classList.toggle("is-tree-modal-open", hasOpenDrawer || hasOpenCreateSheet);
  }

  function closeCreateSheet() {
    var sheet = document.getElementById("tree-create-sheet");
    var backdrop = document.getElementById("tree-sheet-backdrop");

    if (sheet) {
      sheet.classList.remove("is-open");
      sheet.setAttribute("aria-hidden", "true");
    }
    if (backdrop) backdrop.hidden = true;
  }

  function closeTreeDrawer(restoreFocus) {
    document.querySelectorAll(".tree-reveal-drawer.is-open").forEach(function (drawer) {
      drawer.classList.remove("is-open");
      drawer.setAttribute("aria-hidden", "true");
    });

    document.querySelectorAll("[data-person-reveal][aria-expanded='true']").forEach(function (trigger) {
      trigger.setAttribute("aria-expanded", "false");
      trigger.classList.remove("is-selected");
    });

    var backdrop = document.querySelector(".tree-reveal-backdrop");
    if (backdrop) backdrop.hidden = true;

    setBodyLock();

    if (restoreFocus !== false && activeTrigger && typeof activeTrigger.focus === "function") {
      activeTrigger.focus({ preventScroll: true });
    }
    activeTrigger = null;
  }

  function openTreeDrawer(trigger, event) {
    if (!isTreePage() || !trigger) return false;

    var personId = trigger.getAttribute("data-person-reveal");
    if (!personId) return false;

    var drawer = document.getElementById("tree-reveal-" + personId);
    if (!drawer) return false;

    if (event) {
      if (typeof event.preventDefault === "function") event.preventDefault();
      if (typeof event.stopPropagation === "function") event.stopPropagation();
      event.treeRevealHandled = true;
    }

    closeCreateSheet();
    closeTreeDrawer(false);

    activeTrigger = trigger;
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    trigger.setAttribute("aria-expanded", "true");
    trigger.classList.add("is-selected");

    var backdrop = document.querySelector(".tree-reveal-backdrop");
    if (backdrop) backdrop.hidden = false;

    setBodyLock();

    window.setTimeout(function () {
      var closeButton = drawer.querySelector("[data-tree-reveal-close]");
      if (closeButton && typeof closeButton.focus === "function") {
        closeButton.focus({ preventScroll: true });
      }
    }, 80);

    return true;
  }

  window.openTreePersonDrawer = openTreeDrawer;

  document.addEventListener("touchstart", function (event) {
    var trigger = closestRevealTrigger(event.target);
    if (!trigger || !isTreePage()) return;

    var touch = event.changedTouches && event.changedTouches[0];
    if (!touch) return;

    touchStart = {
      trigger: trigger,
      x: touch.clientX,
      y: touch.clientY
    };
  }, { capture: true, passive: true });

  document.addEventListener("touchend", function (event) {
    if (!touchStart || !isTreePage()) return;

    var touch = event.changedTouches && event.changedTouches[0];
    if (!touch) {
      touchStart = null;
      return;
    }

    var endTrigger = closestRevealTrigger(event.target);
    var start = touchStart;
    touchStart = null;

    var movedX = Math.abs(touch.clientX - start.x);
    var movedY = Math.abs(touch.clientY - start.y);

    if (endTrigger === start.trigger && movedX <= 24 && movedY <= 24) {
      openTreeDrawer(start.trigger, event);
    }
  }, { capture: true, passive: false });

  document.addEventListener("click", function (event) {
    var closeTarget = event.target.closest ? event.target.closest("[data-tree-reveal-close]") : null;
    if (closeTarget && isTreePage()) {
      event.preventDefault();
      event.stopPropagation();
      closeTreeDrawer();
      return;
    }

    var trigger = closestRevealTrigger(event.target);
    if (trigger) {
      openTreeDrawer(trigger, event);
    }
  }, true);

  document.addEventListener("keydown", function (event) {
    if (!isTreePage()) return;

    if (event.key === "Escape") {
      closeTreeDrawer();
      return;
    }

    if (event.key !== "Enter" && event.key !== " ") return;

    var trigger = closestRevealTrigger(event.target);
    if (trigger) {
      openTreeDrawer(trigger, event);
    }
  }, true);
})();
