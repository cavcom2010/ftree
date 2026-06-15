(function () {
  var activeRevealTrigger = null;
  var activeCreateTrigger = null;
  var rowUpdateTimers = new WeakMap();
  var cardPointerStart = null;
  var suppressNextCardClick = false;

  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }

  function qsa(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  function notify(message) {
    if (typeof window.showToast === "function") {
      window.showToast(message);
    }
  }

  function getRevealTrigger(target) {
    if (!target || typeof target.closest !== "function") return null;
    return target.closest("[data-person-reveal]");
  }

  function hasOpenModal() {
    return !!qs(".tree-reveal-drawer.is-open") || !!qs("#tree-create-sheet.is-open");
  }

  function syncModalLock() {
    document.body.classList.toggle("is-tree-modal-open", hasOpenModal());
  }

  function focusSafely(element) {
    if (element && typeof element.focus === "function") {
      element.focus({ preventScroll: true });
    }
  }

  function updateRowState(track) {
    if (!track) return;
    var shell = track.closest("[data-row-shell]");
    if (!shell) return;

    var maxScroll = Math.max(0, track.scrollWidth - track.clientWidth);
    var atStart = track.scrollLeft <= 2;
    var atEnd = maxScroll <= 2 || track.scrollLeft >= maxScroll - 2;
    var leftButton = qs('[data-row-scroll="left"]', shell);
    var rightButton = qs('[data-row-scroll="right"]', shell);
    var rowContent = shell.parentElement;
    var progress = qs("[data-row-progress]", rowContent);
    var visibleRatio = track.scrollWidth ? Math.min(1, track.clientWidth / track.scrollWidth) : 1;
    var travelRatio = maxScroll ? track.scrollLeft / maxScroll : 0;

    shell.classList.toggle("is-at-start", atStart);
    shell.classList.toggle("is-at-end", atEnd);
    if (rowContent) rowContent.classList.toggle("is-scrollable", maxScroll > 2);
    if (leftButton) leftButton.disabled = atStart;
    if (rightButton) rightButton.disabled = atEnd;
    if (progress) {
      progress.style.width = Math.max(18, visibleRatio * 100) + "%";
      progress.style.transform = "translateX(" + travelRatio * (100 / Math.max(visibleRatio, 0.01) - 100) + "%)";
    }
  }

  function scheduleRowUpdate(track) {
    window.clearTimeout(rowUpdateTimers.get(track));
    rowUpdateTimers.set(track, window.setTimeout(function () {
      updateRowState(track);
    }, 60));
  }

  function updateAllRows() {
    qsa("[data-tree-row-track]").forEach(updateRowState);
  }

  function openCreateSheet(trigger) {
    var sheet = qs("#tree-create-sheet");
    var backdrop = qs("#tree-sheet-backdrop");
    if (!sheet || !backdrop) return;

    closeRevealDrawers(false);
    activeCreateTrigger = trigger || null;
    sheet.classList.add("is-open");
    sheet.setAttribute("aria-hidden", "false");
    backdrop.hidden = false;
    syncModalLock();

    window.setTimeout(function () {
      focusSafely(qs("[data-create-sheet-close]", sheet) || qs("button", sheet));
    }, 80);
  }

  function closeCreateSheet(restoreFocus) {
    var sheet = qs("#tree-create-sheet");
    var backdrop = qs("#tree-sheet-backdrop");
    if (!sheet || !backdrop) return;

    sheet.classList.remove("is-open");
    sheet.setAttribute("aria-hidden", "true");
    backdrop.hidden = true;
    syncModalLock();

    if (restoreFocus !== false) {
      focusSafely(activeCreateTrigger);
    }
    activeCreateTrigger = null;
  }

  function closeRevealDrawers(restoreFocus) {
    qsa(".tree-reveal-drawer.is-open").forEach(function (drawer) {
      drawer.classList.remove("is-open");
      drawer.setAttribute("aria-hidden", "true");
    });
    qsa("[data-person-reveal][aria-expanded='true']").forEach(function (trigger) {
      trigger.setAttribute("aria-expanded", "false");
      trigger.classList.remove("is-selected");
    });

    var backdrop = qs(".tree-reveal-backdrop");
    if (backdrop) backdrop.hidden = true;
    syncModalLock();

    if (restoreFocus !== false) {
      focusSafely(activeRevealTrigger);
    }
    activeRevealTrigger = null;
  }

  function openRevealDrawer(trigger) {
    if (!trigger) return;
    var personId = trigger.getAttribute("data-person-reveal");
    var drawer = qs("#tree-reveal-" + personId);
    var backdrop = qs(".tree-reveal-backdrop");
    if (!drawer) return;

    closeCreateSheet(false);
    closeRevealDrawers(false);
    activeRevealTrigger = trigger;
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    trigger.setAttribute("aria-expanded", "true");
    trigger.classList.add("is-selected");
    if (backdrop) backdrop.hidden = false;
    syncModalLock();

    window.setTimeout(function () {
      focusSafely(qs("[data-tree-reveal-close]", drawer) || drawer);
    }, 80);
  }

  function activateRevealTrigger(trigger, event) {
    if (!trigger) return false;
    if (event && typeof event.preventDefault === "function") {
      event.preventDefault();
    }
    if (event && typeof event.stopPropagation === "function") {
      event.stopPropagation();
    }
    openRevealDrawer(trigger);
    return true;
  }

  function activateRevealTab(button) {
    var drawer = button.closest(".tree-reveal-drawer");
    var panelId = button.getAttribute("data-reveal-tab");
    if (!drawer || !panelId) return;

    qsa("[data-reveal-tab]", drawer).forEach(function (tab) {
      var isActive = tab === button;
      tab.classList.toggle("is-active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    qsa("[data-reveal-panel]", drawer).forEach(function (panel) {
      var isActive = panel.id === panelId;
      panel.classList.toggle("is-active", isActive);
      panel.hidden = !isActive;
    });
  }

  function scrollRow(button) {
    var shell = button.closest("[data-row-shell]");
    var track = shell ? qs("[data-tree-row-track]", shell) : null;
    if (!track) return;

    var direction = button.getAttribute("data-row-scroll") === "left" ? -1 : 1;
    track.scrollBy({ left: direction * Math.round(track.clientWidth * 0.82), behavior: "smooth" });
    scheduleRowUpdate(track);
  }

  function scrollFocusedTrack(track, direction) {
    track.scrollBy({ left: direction * Math.round(track.clientWidth * 0.72), behavior: "smooth" });
    scheduleRowUpdate(track);
  }

  function focusAnchorRow() {
    var anchorRow = qs(".tree-generation-row.is-anchor-row");
    if (anchorRow) {
      anchorRow.scrollIntoView({ behavior: "smooth", block: "center" });
      anchorRow.classList.add("is-selected-row");
      window.setTimeout(function () {
        anchorRow.classList.remove("is-selected-row");
      }, 1100);
    }
  }

  function openAnchorCard() {
    var anchorCard = qs(".tree-person-card.is-anchor") || qs("[data-person-reveal]");

    if (!anchorCard) {
      focusAnchorRow();
      return;
    }

    anchorCard.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
    window.setTimeout(function () {
      openRevealDrawer(anchorCard);
    }, 180);
  }

  function toggleGeneration(button) {
    var row = button.closest(".tree-generation-row");
    var contentId = button.getAttribute("aria-controls");
    var content = contentId ? qs("#" + contentId) : qs("[data-generation-content]", row);
    if (!row || !content) return;

    var shouldOpen = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
    row.classList.toggle("is-collapsed", !shouldOpen);
    content.hidden = !shouldOpen;
    if (shouldOpen) {
      qsa("[data-tree-row-track]", content).forEach(updateRowState);
    }
  }

  document.addEventListener("pointerdown", function (event) {
    var revealTrigger = getRevealTrigger(event.target);
    if (!revealTrigger || event.pointerType === "mouse") return;
    cardPointerStart = {
      pointerId: event.pointerId,
      trigger: revealTrigger,
      x: event.clientX,
      y: event.clientY
    };
  }, { passive: true });

  document.addEventListener("pointerup", function (event) {
    if (!cardPointerStart || cardPointerStart.pointerId !== event.pointerId) return;

    var start = cardPointerStart;
    cardPointerStart = null;

    var movedX = Math.abs(event.clientX - start.x);
    var movedY = Math.abs(event.clientY - start.y);
    var endedOnSameCard = getRevealTrigger(event.target) === start.trigger;

    if (endedOnSameCard && movedX <= 8 && movedY <= 8) {
      suppressNextCardClick = true;
      activateRevealTrigger(start.trigger, event);
      window.setTimeout(function () {
        suppressNextCardClick = false;
      }, 300);
    }
  });

  document.addEventListener("pointercancel", function () {
    cardPointerStart = null;
  });

  document.addEventListener("click", function (event) {
    var revealTrigger = getRevealTrigger(event.target);
    if (revealTrigger) {
      if (suppressNextCardClick) {
        suppressNextCardClick = false;
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      activateRevealTrigger(revealTrigger, event);
      return;
    }

    var revealTab = event.target.closest("[data-reveal-tab]");
    if (revealTab) {
      activateRevealTab(revealTab);
      return;
    }

    if (event.target.closest("[data-tree-reveal-close]")) {
      closeRevealDrawers();
      return;
    }

    var rowScroll = event.target.closest("[data-row-scroll]");
    if (rowScroll) {
      scrollRow(rowScroll);
      return;
    }

    var generationToggle = event.target.closest("[data-generation-toggle]");
    if (generationToggle) {
      toggleGeneration(generationToggle);
      return;
    }

    var openAnchorTrigger = event.target.closest("[data-tree-open-anchor]");
    if (openAnchorTrigger) {
      openAnchorCard();
      return;
    }

    var createTrigger = event.target.closest("[data-create-sheet-trigger]");
    if (createTrigger) {
      openCreateSheet(createTrigger);
      return;
    }

    if (event.target.closest("[data-create-sheet-close]")) {
      closeCreateSheet();
      if (event.target.closest("[data-tree-scroll-anchor]")) {
        focusAnchorRow();
      }
      return;
    }

    if (event.target.closest("[data-tree-scroll-anchor]")) {
      focusAnchorRow();
      return;
    }

    var toastTarget = event.target.closest("[data-tree-toast]");
    if (toastTarget) {
      notify(toastTarget.getAttribute("data-tree-toast"));
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeCreateSheet();
      closeRevealDrawers();
      return;
    }

    var track = event.target.closest ? event.target.closest("[data-tree-row-track]") : null;
    if (!track) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      scrollFocusedTrack(track, -1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      scrollFocusedTrack(track, 1);
    }
  });

  qsa("[data-tree-row-track]").forEach(function (track) {
    track.addEventListener("scroll", function () {
      scheduleRowUpdate(track);
    }, { passive: true });
  });

  window.addEventListener("resize", updateAllRows);
  window.addEventListener("load", updateAllRows);
  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail && event.detail.target && event.detail.target.id === "tree-create-sheet") {
      syncModalLock();
      focusSafely(qs("[data-create-sheet-close]", event.detail.target) || qs("button", event.detail.target));
    }
    updateAllRows();
  });
  updateAllRows();
})();