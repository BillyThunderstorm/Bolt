let kills = 0;
let wins = 0;
let deaths = 0;

function flash(element) {
    element.classList.add("flash");

    setTimeout(() => {
        element.classList.remove("flash");
    }, 400);
}

function addKill() {
    kills++;

    const killElement = document.getElementById("kills");
    killElement.innerText = kills;

    flash(killElement);

    const tallyContainer = document.getElementById("kill-tallies");

    const tally = document.createElement("div");
    tally.classList.add("tally");

    tallyContainer.appendChild(tally);
}

function addWin() {
    wins++;

    const winElement = document.getElementById("wins");
    winElement.innerText = wins;

    flash(winElement);
}

function addDeath() {
    deaths++;

    const deathElement = document.getElementById("deaths");
    deathElement.innerText = deaths;

    flash(deathElement);
}

document.addEventListener("keydown", (event) => {

    if(event.key === "1") {
        addKill();
    }

    if(event.key === "2") {
        addWin();
    }

    if(event.key === "3") {
        addDeath();
    }

});
