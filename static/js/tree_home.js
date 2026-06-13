(function () {
    function notify(message) {
        if (typeof window.showToast === "function") {
            window.showToast(message);
        }
    }

    function openCreateSheet() {
        var sheet = document.getElementById("tree-create-sheet");
        var backdrop = document.getElementById("tree-sheet-backdrop");
        if (!sheet || !backdrop) return;
        sheet.classList.add("is-open");
        sheet.setAttribute("aria-hidden", "false");
        backdrop.hidden = false;
    }

    function closeCreateSheet() {
        var sheet = document.getElementById("tree-create-sheet");
        var backdrop = document.getElementById("tree-sheet-backdrop");
        if (!sheet || !backdrop) return;
        sheet.classList.remove("is-open");
        sheet.setAttribute("aria-hidden", "true");
        backdrop.hidden = true;
    }

    function toggleGeneration(button) {
        var section = button.closest("[data-generation-section]");
        if (!section) return;
        var isOpen = section.classList.toggle("is-open");
        button.setAttribute("aria-expanded", String(isOpen));
        notify(isOpen ? "Generation opened" : "Generation collapsed");
    }

    function openBranch(trigger) {
        var panelId = trigger.getAttribute("data-branch-trigger");
        var panel = document.getElementById(panelId);
        if (!panel) return;
        var shouldOpen = panel.hidden;
        panel.hidden = !shouldOpen;
        trigger.setAttribute("aria-expanded", String(shouldOpen));
        notify(shouldOpen ? "Branch revealed" : "Branch hidden");
    }

    document.addEventListener("click", function (event) {
        var generationToggle = event.target.closest(".generation-toggle");
        if (generationToggle) {
            toggleGeneration(generationToggle);
            return;
        }

        var expandAll = event.target.closest("[data-expand-all-generations]");
        if (expandAll) {
            document.querySelectorAll("[data-generation-section]").forEach(function (section) {
                section.classList.add("is-open");
                var button = section.querySelector(".generation-toggle");
                if (button) button.setAttribute("aria-expanded", "true");
            });
            notify("All generations revealed");
            return;
        }

        var collapseAll = event.target.closest("[data-collapse-all-generations]");
        if (collapseAll) {
            document.querySelectorAll("[data-generation-section]").forEach(function (section, index) {
                var shouldOpen = index === 0;
                section.classList.toggle("is-open", shouldOpen);
                var button = section.querySelector(".generation-toggle");
                if (button) button.setAttribute("aria-expanded", String(shouldOpen));
            });
            notify("Focused on the root branch");
            return;
        }

        var branchTrigger = event.target.closest("[data-branch-trigger]");
        if (branchTrigger) {
            openBranch(branchTrigger);
            return;
        }

        var branchClose = event.target.closest("[data-branch-close]");
        if (branchClose) {
            var closePanel = document.getElementById(branchClose.getAttribute("data-branch-close"));
            if (closePanel) closePanel.hidden = true;
            notify("Branch hidden");
            return;
        }

        if (event.target.closest("[data-create-sheet-trigger]")) {
            openCreateSheet();
            return;
        }

        if (event.target.closest("[data-create-sheet-close]")) {
            closeCreateSheet();
            return;
        }

        var toastTarget = event.target.closest("[data-tree-toast]");
        if (toastTarget) {
            notify(toastTarget.getAttribute("data-tree-toast"));
            return;
        }

        if (event.target.closest("[data-tree-search-trigger]")) {
            notify("Relative search is ready for backend search.");
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeCreateSheet();
        }
    });
})();
