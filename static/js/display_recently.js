(function() {
    let container = document.querySelector(".recently_watch");
    if (!container) return;
    let data = JSON.parse(localStorage.getItem("recently_watched") || "[]");

    if (data.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted); grid-column: 1/-1; text-align: center;">У вас пока нет просмотренных аниме.</p>';
    }

    for (let item of data) {
        let card = document.createElement("a");
        card.classList.add("card");
        card.href = `/download/sh/${item[0]}/`;

        let img = document.createElement("img");
        img.src = item[2];
        img.loading = "lazy";

        let textWrap = document.createElement("div");
        let text = document.createElement("h6");
        text.textContent = item[1];
        textWrap.appendChild(text);

        card.appendChild(img);
        card.appendChild(textWrap);
        container.appendChild(card);
    }
})();