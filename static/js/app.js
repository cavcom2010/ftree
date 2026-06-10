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
    var name = card.getAttribute("data-person-name") || "";
    var meta = card.getAttribute("data-person-meta") || "";
    var avatar = card.getAttribute("data-person-avatar") || "?";
    var nextLane = card.getAttribute("data-next-lane") || "";
    var rowId = card.getAttribute("data-row-id") || "";
    var cardId = card.getAttribute("data-card-id") || "";

    document.querySelectorAll(".person-card").forEach(function (c) {
        c.classList.remove("selected");
    });
    card.classList.add("selected");

    var drawerAvatar = document.getElementById("drawer-avatar");
    var drawerName = document.getElementById("drawer-name");
    var drawerMeta = document.getElementById("drawer-meta");

    if (drawerAvatar) {
        drawerAvatar.textContent = avatar;
        drawerAvatar.className = "person-drawer-avatar";
        var cardAvatar = card.querySelector(".person-card-avatar");
        if (cardAvatar && cardAvatar.classList.contains("male")) {
            drawerAvatar.classList.add("male");
        } else if (cardAvatar && cardAvatar.classList.contains("female")) {
            drawerAvatar.classList.add("female");
        }
    }
    if (drawerName) drawerName.textContent = name;
    if (drawerMeta) drawerMeta.textContent = meta;

    openDrawer();

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

function openDrawer() {
    document.getElementById("person-drawer").classList.add("open");
    document.getElementById("drawer-overlay").classList.add("open");
}

function closeDrawer() {
    document.getElementById("person-drawer").classList.remove("open");
    document.getElementById("drawer-overlay").classList.remove("open");
}
