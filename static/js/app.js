document.addEventListener("DOMContentLoaded", function () {
    var navItems = document.querySelectorAll(".nav-item");
    navItems.forEach(function (item) {
        item.addEventListener("click", function () {
            if (item.classList.contains("nav-add")) return;
            navItems.forEach(function (el) { el.classList.remove("active"); });
            item.classList.add("active");
        });
    });

    var snapshot = document.querySelector(".tree-snapshot");
    if (snapshot) {
        snapshot.addEventListener("click", function (e) {
            var card = e.target.closest(".person-card");
            if (!card) return;
            selectPerson(card);
        });
    }
});

document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail.target.id === "person-drawer") {
        event.detail.target.classList.add("show");
        document.getElementById("drawer-overlay").classList.add("show");
    }
});

function showToast(message) {
    var existing = document.querySelector(".toast");
    if (existing) existing.remove();
    var toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(function () {
        toast.classList.add("show");
    });
    setTimeout(function () {
        toast.classList.remove("show");
        setTimeout(function () { toast.remove(); }, 300);
    }, 2000);
}

function selectPerson(card) {
    var nextLane = card.getAttribute("data-next-lane") || "";
    var rowId = card.getAttribute("data-row-id") || "";
    var cardId = card.getAttribute("data-card-id") || "";

    document.querySelectorAll(".person-card").forEach(function (c) {
        c.classList.remove("selected");
    });
    card.classList.add("selected");

    if (nextLane) {
        revealLane(nextLane, rowId, cardId);
    }

    if (rowId && cardId) {
        centerInRow(rowId, cardId);
    }
}

function revealLane(laneId, parentRowId, parentId) {
    var lane = document.getElementById(laneId);
    if (lane && lane.style.display === "none") {
        lane.style.display = "";
        setTimeout(function () {
            lane.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }, 100);
    }
}

function centerInRow(rowId, cardId) {
    var row = document.getElementById(rowId);
    var card = document.getElementById(cardId);
    if (!row || !card) return;
    var rowWidth = row.clientWidth;
    var cardLeft = card.offsetLeft;
    var cardWidth = card.offsetWidth;
    var target = cardLeft + cardWidth / 2 - rowWidth / 2;
    row.scrollTo({ left: target, behavior: "smooth" });
}

function revealAll() {
    document.querySelectorAll(".gen-lane").forEach(function (lane) {
        lane.style.display = "";
    });
}

function closeDrawer() {
    document.getElementById("person-drawer").classList.remove("show");
    document.getElementById("drawer-overlay").classList.remove("show");
}
