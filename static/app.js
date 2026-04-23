const STORAGE_KEY = "anidex-day1-discovered";
const SCAN_ENDPOINT = "/api/recognize";
const BROWSER_ANIMAL_MAP = {
    dog: "Dog",
    cat: "Cat",
    cow: "Cow",
    horse: "Horse",
    elephant: "Elephant",
    bird: "Bird",
    kite: "Kite",
    crow: "Crow",
    pigeon: "Pigeon",
    sparrow: "Sparrow",
    parrot: "Parrot",
    duck: "Duck",
};

let browserRecognizerPromise = null;
let animalsPromise = null;
let currentSuggestion = null;
let currentCameraStream = null;
const boot = window.ANIDEX_BOOTSTRAP || {};
let serverDiscovered = new Set(Array.isArray(boot.discovered) ? boot.discovered : []);
const isAuthenticated = Boolean(boot.isAuthenticated);

function readDiscovered() {
    if (isAuthenticated) {
        return [...serverDiscovered];
    }
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
    } catch (error) {
        return [];
    }
}

async function writeDiscovered(items, action = "toggle", animalId = null) {
    const uniqueItems = [...new Set(items)];
    if (isAuthenticated) {
        const response = await fetch("/api/progress", {
            method: action === "clear" ? "DELETE" : "POST",
            headers: { "Content-Type": "application/json" },
            body: action === "clear"
                ? JSON.stringify({ action: "clear" })
                : JSON.stringify({ action, animal_id: animalId }),
        });
        const data = await response.json();
        if (response.ok) {
            serverDiscovered = new Set(data.discovered || uniqueItems);
            return;
        }
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(uniqueItems));
}

function updateProgress() {
    const discovered = readDiscovered();
    const count = document.querySelectorAll("[data-discover-button]").length
        ? new Set(discovered).size
        : discovered.length;
    const progressNode = document.getElementById("progress-count");
    if (progressNode) {
        const total = document.querySelectorAll("[data-animal-card]").length;
        progressNode.textContent = `${Math.min(count, total)}/${total}`;
    }
}

function syncButtons() {
    const discovered = new Set(readDiscovered());
    document.querySelectorAll("[data-discover-button]").forEach((button) => {
        const animalId = button.dataset.animalId;
        const found = discovered.has(animalId);
        button.classList.toggle("is-found", found);
        button.textContent = found ? "Discovered" : button.closest(".entry-card") ? "Mark as Discovered" : "Mark Found";
    });
}

async function toggleAnimal(animalId) {
    const discovered = new Set(readDiscovered());
    if (discovered.has(animalId)) {
        discovered.delete(animalId);
    } else {
        discovered.add(animalId);
    }
    await writeDiscovered([...discovered], "toggle", animalId);
    syncButtons();
    updateProgress();
}

function initSearch() {
    const input = document.getElementById("search-input");
    if (!input) {
        return;
    }

    input.addEventListener("input", () => {
        const term = input.value.trim().toLowerCase();
        document.querySelectorAll("[data-animal-card]").forEach((card) => {
            const haystack = card.dataset.search || "";
            card.classList.toggle("is-hidden", term !== "" && !haystack.includes(term));
        });
    });
}

async function startCamera() {
    const video = document.getElementById("camera-preview");
    const status = document.getElementById("scan-status");
    const result = document.getElementById("scan-result");
    if (!video || !status) {
        return;
    }

    try {
        if (!window.isSecureContext && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
            status.textContent = "Camera needs HTTPS on phones. Open the secure version of Anidex.";
            return;
        }
        if (currentCameraStream) {
            currentCameraStream.getTracks().forEach((track) => track.stop());
        }
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" } },
            audio: false,
        });
        currentCameraStream = stream;
        video.srcObject = stream;
        status.textContent = "Camera ready. Frame an animal and tap Capture.";
        if (result) {
            result.classList.add("is-hidden");
        }
    } catch (error) {
        const reason = error && error.message ? error.message : "Camera access was blocked or unavailable.";
        status.textContent = `Camera failed: ${reason}`;
    }
}

function stopCamera() {
    if (currentCameraStream) {
        currentCameraStream.getTracks().forEach((track) => track.stop());
        currentCameraStream = null;
    }

    const video = document.getElementById("camera-preview");
    if (video) {
        video.srcObject = null;
    }
}

async function loadBrowserRecognizer() {
    if (window.cocoSsd) {
        if (!browserRecognizerPromise) {
            browserRecognizerPromise = window.cocoSsd.load();
        }
        return browserRecognizerPromise;
    }
    return null;
}

async function loadAnimals() {
    if (!animalsPromise) {
        animalsPromise = fetch("/api/animals").then((response) => response.json());
    }
    return animalsPromise;
}

function normalizeText(value) {
    return String(value || "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "");
}

function getSuggestedMatch(label, animals) {
    const normalizedLabel = normalizeText(label);
    const exact = animals.find((animal) => normalizeText(animal.name) === normalizedLabel);
    if (exact) {
        return exact;
    }

    const broadMatches = animals.filter((animal) => {
        const name = normalizeText(animal.name);
        const category = normalizeText(animal.category);
        return name.includes(normalizedLabel) || normalizedLabel.includes(name) || category === normalizedLabel;
    });

    if (broadMatches.length > 0) {
        return broadMatches[0];
    }

    return animals.find((animal) => animal.rarity !== "Legendary") || animals[0] || null;
}

function pickBrowserLabel(predictions) {
    if (!predictions || predictions.length === 0) {
        return null;
    }

    const best = predictions[0];
    const raw = String(best.class || "").toLowerCase();
    const mapped = BROWSER_ANIMAL_MAP[raw] || best.class;
    return {
        label: mapped,
        confidence: best.score || 0,
        raw,
        predictions,
    };
}

function renderSuggestionPanel(suggestion) {
    const confirmPanel = document.getElementById("confirm-panel");
    const confirmName = document.getElementById("confirm-name");
    const confirmDesc = document.getElementById("confirm-desc");
    const openEntry = document.getElementById("open-entry");

    if (!confirmPanel || !confirmName || !confirmDesc || !openEntry) {
        return;
    }

    if (!suggestion) {
        confirmPanel.classList.add("is-hidden");
        return;
    }

    currentSuggestion = suggestion;
    confirmName.textContent = suggestion.name;
    confirmDesc.textContent = `${suggestion.category} · ${suggestion.habitat}`;
    openEntry.href = `/animal/${suggestion.id}`;
    confirmPanel.classList.remove("is-hidden");
}

async function markSuggestedAnimal() {
    if (!currentSuggestion) {
        return;
    }

    const discovered = new Set(readDiscovered());
    discovered.add(currentSuggestion.id);
    await writeDiscovered([...discovered], "add", currentSuggestion.id);

    const status = document.getElementById("scan-status");
    if (status) {
        status.textContent = `${currentSuggestion.name} added to your Dex.`;
    }
    syncButtons();
    updateProgress();
}

async function captureAndRecognize() {
    const video = document.getElementById("camera-preview");
    const canvas = document.getElementById("capture-canvas");
    const status = document.getElementById("scan-status");
    const result = document.getElementById("scan-result");
    if (!video || !canvas || !status) {
        return;
    }

    if (!video.srcObject) {
        status.textContent = "Start the camera first.";
        return;
    }

    const width = video.videoWidth || 1280;
    const height = video.videoHeight || 720;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, width, height);

    status.textContent = "Analyzing image...";

    let data = null;
    try {
        const model = await loadBrowserRecognizer();
        if (model) {
            const predictions = await model.detect(canvas);
            const chosen = pickBrowserLabel(predictions);
            if (chosen) {
                data = {
                    detected: chosen.label,
                    confidence: chosen.confidence,
                    alternatives: predictions.slice(1, 4).map((item) => ({
                        name: BROWSER_ANIMAL_MAP[String(item.class || "").toLowerCase()] || item.class,
                        confidence: item.score || 0,
                    })),
                    note: chosen.raw === "bird"
                        ? "Bird detected. The model is broad, so use the Dex to confirm the exact bird."
                        : "Model prediction from the browser. Tap the best match in the Dex to confirm.",
                };
            }
        }
    } catch (error) {
        data = null;
    }

    if (!data) {
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
        const formData = new FormData();
        formData.append("image", blob, "scan.jpg");
        const response = await fetch(SCAN_ENDPOINT, {
            method: "POST",
            body: formData,
        });
        data = await response.json();
        if (!response.ok) {
            status.textContent = data.error || "Recognition failed.";
            return;
        }
    }

    status.textContent = "Scan complete.";
    if (result) {
        result.classList.remove("is-hidden");
        document.getElementById("detected-name").textContent = `Detected: ${data.detected}`;
        document.getElementById("detected-note").textContent = data.note || "";
        document.getElementById("detected-alt").textContent = (data.alternatives || [])
            .map((item) => `${item.name} ${Math.round((item.confidence || 0) * 100)}%`)
            .join(" | ");
    }

    const animals = await loadAnimals();
    renderSuggestionPanel(getSuggestedMatch(data.detected, animals));
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-discover-button]").forEach((button) => {
        button.addEventListener("click", () => toggleAnimal(button.dataset.animalId));
    });

    const clearButton = document.getElementById("clear-progress");
    if (clearButton) {
        clearButton.addEventListener("click", async () => {
            await writeDiscovered([], "clear");
            syncButtons();
            updateProgress();
        });
    }

    if (isAuthenticated) {
        fetch("/api/progress")
            .then((response) => response.json())
            .then((data) => {
                serverDiscovered = new Set(data.discovered || []);
                try {
                    const localItems = JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
                    if (serverDiscovered.size === 0 && localItems.length > 0) {
                        localItems.forEach((animalId) => {
                            fetch("/api/progress", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ action: "add", animal_id: animalId }),
                            }).catch(() => {});
                        });
                        serverDiscovered = new Set(localItems);
                    }
                } catch (error) {
                    // Ignore bad guest storage and keep the server state.
                }
                syncButtons();
                updateProgress();
            })
            .catch(() => {});
    }

    initSearch();
    syncButtons();
    updateProgress();

    const startCameraButton = document.getElementById("start-camera");
    if (startCameraButton) {
        startCameraButton.addEventListener("click", startCamera);
    }

    const captureButton = document.getElementById("capture-photo");
    if (captureButton) {
        captureButton.addEventListener("click", () => {
            const status = document.getElementById("scan-status");
            if (status) {
                status.textContent = "Captured frame. Ready to recognize.";
            }
        });
    }

    const recognizeButton = document.getElementById("upload-scan");
    if (recognizeButton) {
        recognizeButton.addEventListener("click", captureAndRecognize);
    }

    const confirmFoundButton = document.getElementById("confirm-found");
    if (confirmFoundButton) {
        confirmFoundButton.addEventListener("click", markSuggestedAnimal);
    }

    const openHomeCamera = document.getElementById("home-camera-open");
    const homeCameraModal = document.getElementById("home-camera-modal");
    const closeHomeCamera = document.getElementById("home-camera-close");
    const closeHomeCameraX = document.getElementById("home-camera-x");

    function openModalCamera() {
        if (!homeCameraModal) {
            return;
        }
        homeCameraModal.classList.remove("is-hidden");
        homeCameraModal.setAttribute("aria-hidden", "false");
        startCamera();
    }

    function closeModalCamera() {
        if (!homeCameraModal) {
            return;
        }
        stopCamera();
        homeCameraModal.classList.add("is-hidden");
        homeCameraModal.setAttribute("aria-hidden", "true");
    }

    if (openHomeCamera) {
        openHomeCamera.addEventListener("click", openModalCamera);
    }
    if (closeHomeCamera) {
        closeHomeCamera.addEventListener("click", closeModalCamera);
    }
    if (closeHomeCameraX) {
        closeHomeCameraX.addEventListener("click", closeModalCamera);
    }
});
