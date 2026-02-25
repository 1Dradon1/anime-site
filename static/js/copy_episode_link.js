let episodeButtons = document.getElementsByClassName("episode-number");
let autoMpvToggle = document.getElementById("auto_mpv_toggle");
let shikimori_id = episodeButtons.length > 0 ? episodeButtons[0].getAttribute("data-shikimori-id") : null;

// Инициализация тумблера
if (autoMpvToggle) {
    const isAuto = localStorage.getItem("autoMPV") === "true";
    autoMpvToggle.checked = isAuto;
    autoMpvToggle.addEventListener("change", (e) => {
        localStorage.setItem("autoMPV", e.target.checked);
    });
}

// Слушатель для кнопок серий
for (let item of episodeButtons) {
    item.addEventListener("click", (e) => {
        const isAuto = localStorage.getItem("autoMPV") === "true";
        if (isAuto) {
            fetchAndOpenMPV(e);
        } else {
            window.location.href = item.getAttribute("data-web-url");
        }
    });
}

if (shikimori_id) {
    load_last_watched(shikimori_id);
}

/**
 * Fetches an MPV stream URL for the clicked episode and opens it using the mpv:// protocol handler.
 *
 * Shows user-facing notifications about progress and errors and records the episode as last-watched.
 *
 * @param {Event} event - Click event whose `currentTarget` is the episode button element (must have `data-shikimori-id`, `data-translation-id`, and `value`).
 */
async function fetchAndOpenMPV(event) {
    const episode = event.currentTarget;
    const notification = document.getElementById("copy-notification");
    
    try {
        if (notification) showNotification(notification, "Запрашиваем ссылку...", 5000);
        
        const shikimori_id = episode.getAttribute("data-shikimori-id");
        const translation_id = episode.getAttribute("data-translation-id");
        const ep_value = episode.value;

        const response = await fetch(`/get_episode/${shikimori_id}/${ep_value}/${translation_id}`);

        if (!response.ok) {
            throw new Error(`Ошибка: ${response.status}`);
        }

        const text = await response.text();
        window.location.href = `mpv://${encodeURIComponent(text)}`;
        
        if (notification) showNotification(notification, "Открываю MPV!", 2000);
        
        save_last_watched(shikimori_id, ep_value, translation_id);
    } catch (err) {
        console.error('Ошибка:', err);
        if (notification) showNotification(notification, "Ошибка открытия :(", 3000);
    }
}

/**
 * Show a transient notification by setting the container's `.alert` text, adding the `visible` class, and removing it after a timeout.
 * @param {Element} el - Container element that must contain a child with class `alert`; the `visible` class will be added/removed on this element. 
 * @param {string} text - Message to display inside the container's `.alert` child.
 * @param {number} duration - Time in milliseconds before the notification is hidden.
 */
function showNotification(el, text, duration) {
    el.querySelector(".alert").textContent = text;
    el.classList.add("visible");
    if (el.timeout) clearTimeout(el.timeout);
    el.timeout = setTimeout(() => el.classList.remove("visible"), duration);
}

/**
 * Save the last watched episode and translation for a Shikimori entry and update the UI highlight.
 * Updates the "lastEpisodes" object in localStorage (key "lastEpisodes") mapping `shikimori_id` to `[episode, translation_id]`,
 * then calls highlight_last_watched to reflect the change in the page.
 * @param {string|number} shikimori_id - The Shikimori item identifier.
 * @param {string|number} episode - The episode identifier or number.
 * @param {string|number} translation_id - The translation/voiceover identifier.
 */
function save_last_watched(shikimori_id, episode, translation_id) {
    const data = JSON.parse(localStorage.getItem("lastEpisodes") || "{}");
    data[shikimori_id] = [episode, translation_id];
    localStorage.setItem("lastEpisodes", JSON.stringify(data));
    highlight_last_watched(shikimori_id, episode, translation_id);
}

/**
 * Mark the episode button that matches the provided episode and translation as the last watched and clear that mark from all other episode buttons.
 * @param {string} shikimoriId - Identifier of the anime on Shikimori (contextual; not used to select buttons here).
 * @param {string|number} episode - Episode value to match against each button's value.
 * @param {string} translationId - Translation identifier to match against each button's `data-translation-id` attribute.
 */
function highlight_last_watched(shikimoriId, episode, translationId) {
    for (let btn of episodeButtons) {
        if (btn.getAttribute("data-translation-id") === translationId && btn.value === episode) {
            btn.classList.add("last-watched");
        } else {
            btn.classList.remove("last-watched");
        }
    }
}

/**
 * Loads the last-watched episode for a given Shikimori ID from localStorage and highlights it in the UI.
 * @param {string|number} shikimori_id - The Shikimori item identifier used as the key in stored last-episodes data.
 */
function load_last_watched(shikimori_id) {
    const data = JSON.parse(localStorage.getItem("lastEpisodes") || "{}");
    if (data[shikimori_id]) {
        highlight_last_watched(shikimori_id, data[shikimori_id][0], data[shikimori_id][1]);
    }
}
