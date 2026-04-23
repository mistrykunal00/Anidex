const STORAGE_KEYS = {
    accounts: "anidex-static-accounts",
    currentUser: "anidex-static-current-user",
    guestProgress: "anidex-static-guest-progress",
    progressPrefix: "anidex-static-progress:",
};

const CATEGORY_EMOJI = {
    Mammal: "\u{1F43E}",
    Bird: "\u{1F426}",
    Reptile: "\u{1F98E}",
    Amphibian: "\u{1F438}",
    Fish: "\u{1F41F}",
    Crustacean: "\u{1F980}",
    Mollusk: "\u{1F40C}",
    Insect: "\u{1F41D}",
    Arachnid: "\u{1F577}\uFE0F",
    Zoo: "\u{1F981}",
};

const BROAD_LABEL_MAP = {
    dog: "Dog",
    cat: "Cat",
    cow: "Cow",
    horse: "Horse",
    elephant: "Elephant",
    bird: "Crow",
    crow: "Crow",
    kite: "Kite",
    pigeon: "Pigeon",
    sparrow: "Sparrow",
    parrot: "Parrot",
    duck: "Duck",
    sheep: "Sheep",
    goat: "Goat",
    bear: "Bear",
    zebra: "Zebra",
    giraffe: "Giraffe",
    lion: "Lion",
    tiger: "Tiger",
};

const ANIMALS = Array.isArray(window.ANIDEX_ANIMALS) ? window.ANIDEX_ANIMALS : [];

const state = {
    animals: ANIMALS,
    accounts: loadJson(STORAGE_KEYS.accounts, []),
    currentUser: loadJson(STORAGE_KEYS.currentUser, null),
    discovered: [],
    currentSuggestion: null,
    currentEntry: null,
    currentCameraStream: null,
    recognizerPromise: null,
    recognizerError: null,
};

function loadJson(key, fallback) {
    try {
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
    } catch (_error) {
        return fallback;
    }
}

function saveJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

function normalizeText(value) {
    return String(value || "")
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "");
}

function normalizeEmail(value) {
    return String(value || "").trim().toLowerCase();
}

function getProgressKey(user = state.currentUser) {
    if (user && user.email) {
        return `${STORAGE_KEYS.progressPrefix}${normalizeEmail(user.email)}`;
    }
    return STORAGE_KEYS.guestProgress;
}

function loadProgress(user = state.currentUser) {
    return loadJson(getProgressKey(user), []);
}

function saveProgress(progress, user = state.currentUser) {
    saveJson(getProgressKey(user), progress);
}

function setCurrentUser(user) {
    state.currentUser = user ? { username: user.username, email: normalizeEmail(user.email), createdAt: user.createdAt } : null;
    saveJson(STORAGE_KEYS.currentUser, state.currentUser);
    state.discovered = loadProgress(state.currentUser);
    syncFoundStates();
    updateProgress();
    renderProfile();
}

function hydrateCurrentUser() {
    if (!state.currentUser) {
        state.discovered = loadProgress(null);
        return;
    }

    const match = state.accounts.find((account) => account.email === normalizeEmail(state.currentUser.email));
    if (!match) {
        state.currentUser = null;
        saveJson(STORAGE_KEYS.currentUser, null);
        state.discovered = loadProgress(null);
        return;
    }

    state.currentUser = {
        username: match.username,
        email: match.email,
        createdAt: match.createdAt,
    };
    saveJson(STORAGE_KEYS.currentUser, state.currentUser);
    state.discovered = loadProgress(state.currentUser);
}

function decodedEmoji(value) {
    const raw = String(value || "");
    try {
        const decoded = decodeURIComponent(escape(raw));
        return decoded || raw;
    } catch (_error) {
        return raw;
    }
}

function getAnimalEmoji(animal) {
    const decoded = decodedEmoji(animal.emoji);
    if (/[^\x00-\x7F]/.test(decoded)) {
        return decoded;
    }
    return CATEGORY_EMOJI[animal.category] || "\u{1F43E}";
}

function animalById(animalId) {
    return state.animals.find((animal) => animal.id === animalId) || null;
}

function escapeHtml(value) {
    return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}

function foundSet() {
    return new Set(state.discovered);
}

function persistDiscovered(nextDiscovered) {
    state.discovered = [...new Set(nextDiscovered)];
    saveProgress(state.discovered, state.currentUser);
    syncFoundStates();
    updateProgress();
    renderProfile();
}

function toggleAnimal(animalId) {
    const next = new Set(state.discovered);
    if (next.has(animalId)) {
        next.delete(animalId);
    } else {
        next.add(animalId);
    }
    persistDiscovered([...next]);
}

function updateProgress() {
    const progressNode = document.getElementById("progress-count");
    const countNode = document.getElementById("animal-count");
    const total = state.animals.length;
    const found = foundSet().size;

    if (progressNode) {
        progressNode.textContent = `${found}/${total}`;
    }
    if (countNode) {
        countNode.textContent = `${total} entries`;
    }
}

function syncFoundStates() {
    const found = foundSet();
    document.querySelectorAll("[data-animal-card]").forEach((card) => {
        const animalId = card.dataset.animalId;
        card.classList.toggle("is-found", found.has(animalId));
    });

    document.querySelectorAll("[data-discover-button]").forEach((button) => {
        const animalId = button.dataset.animalId;
        const discovered = found.has(animalId);
        button.classList.toggle("is-found", discovered);
        if (button.dataset.mode === "modal") {
            button.textContent = discovered ? "Remove Discovery" : "Mark as Discovered";
        } else {
            button.textContent = discovered ? "Discovered" : "Mark Found";
        }
    });
}

function renderDate() {
    const dateNode = document.getElementById("device-date");
    if (!dateNode) {
        return;
    }

    dateNode.textContent = new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "2-digit",
        year: "numeric",
    }).format(new Date());
}

function renderAnimals() {
    const grid = document.getElementById("animal-grid");
    if (!grid) {
        return;
    }

    grid.innerHTML = state.animals
        .map((animal, index) => {
            const searchText = [
                animal.name,
                animal.scientific_name,
                animal.category,
                animal.habitat,
                animal.status,
                animal.rarity,
                animal.fact,
                animal.description,
            ].join(" ").toLowerCase();

            return `
                <article class="animal-card" data-animal-card data-animal-id="${escapeHtml(animal.id)}" data-search="${escapeHtml(searchText)}">
                    <div class="animal-card-top">
                        <span class="animal-emoji" aria-hidden="true">${escapeHtml(getAnimalEmoji(animal))}</span>
                        <span class="pill">${escapeHtml(animal.category)}</span>
                    </div>
                    <div class="card-topline">
                        <div class="entry-chip">No. ${String(index + 1).padStart(2, "0")}</div>
                        <div class="rarity-chip rarity-${formatRarityClass(animal.rarity)}">${escapeHtml(animal.rarity)}</div>
                    </div>
                    <h3>${escapeHtml(animal.name)}</h3>
                    <p class="scientific-name">${escapeHtml(animal.scientific_name)}</p>
                    <p>${escapeHtml(animal.description)}</p>
                    <p class="entry-fact">${escapeHtml(animal.fact)}</p>
                    <div class="animal-meta">
                        <span>${escapeHtml(animal.habitat)}</span>
                        <span>${escapeHtml(animal.status)}</span>
                    </div>
                    <div class="animal-actions">
                        <button class="primary-button" type="button" data-open-entry data-animal-id="${escapeHtml(animal.id)}">Open Entry</button>
                        <button class="ghost-button discover-button" type="button" data-discover-button data-animal-id="${escapeHtml(animal.id)}">Mark Found</button>
                    </div>
                </article>
            `;
        })
        .join("");
}

function formatRarityClass(rarity) {
    return String(rarity || "")
        .toLowerCase()
        .replaceAll("/", "-")
        .replaceAll(" ", "-");
}

function loadScriptOnce(src) {
    return new Promise((resolve, reject) => {
        const existing = document.querySelector(`script[src="${src}"]`);
        if (existing && existing.dataset.loaded === "true") {
            resolve(existing);
            return;
        }

        if (existing) {
            existing.remove();
        }

        const script = document.createElement("script");
        script.src = src;
        script.async = true;
        script.onload = () => {
            script.dataset.loaded = "true";
            resolve(script);
        };
        script.onerror = () => {
            script.dataset.failed = "true";
            reject(new Error(`Failed to load ${src}`));
        };

        document.head.appendChild(script);
    });
}

async function ensureTensorflowRecognizer() {
    if (!window.tf || !window.cocoSsd) {
        throw new Error("TensorFlow scripts are not available.");
    }
}

function renderProfile() {
    const body = document.getElementById("profile-body");
    if (!body) {
        return;
    }

    if (!state.currentUser) {
        body.innerHTML = `
            <div class="auth-grid">
                <form class="auth-card" id="login-form">
                    <p class="auth-card-title">Sign In</p>
                    <label>
                        <span>Email</span>
                        <input name="email" type="email" required placeholder="you@example.com">
                    </label>
                    <label>
                        <span>Password</span>
                        <input name="password" type="password" required placeholder="••••••••">
                    </label>
                    <button class="primary-button wide-button" type="submit">Sign In</button>
                </form>

                <form class="auth-card" id="signup-form">
                    <p class="auth-card-title">Create Account</p>
                    <label>
                        <span>Username</span>
                        <input name="username" type="text" required minlength="3" placeholder="AnídexFan">
                    </label>
                    <label>
                        <span>Email</span>
                        <input name="email" type="email" required placeholder="you@example.com">
                    </label>
                    <label>
                        <span>Password</span>
                        <input name="password" type="password" required minlength="6" placeholder="At least 6 characters">
                    </label>
                    <button class="ghost-button wide-button" type="submit">Create Account</button>
                </form>
            </div>
            <div id="profile-message" class="auth-alert mt-3">Accounts are stored in this browser for now. We can connect Supabase auth next.</div>
        `;

        const loginForm = document.getElementById("login-form");
        const signupForm = document.getElementById("signup-form");

        if (loginForm) {
            loginForm.addEventListener("submit", (event) => {
                event.preventDefault();
                const form = new FormData(loginForm);
                const email = normalizeEmail(form.get("email"));
                const password = String(form.get("password") || "");
                const account = state.accounts.find((item) => item.email === email && item.password === password);
                const message = document.getElementById("profile-message");

                if (!account) {
                    if (message) {
                        message.textContent = "That email/password combo was not found on this device.";
                    }
                    return;
                }

                setCurrentUser(account);
            });
        }

        if (signupForm) {
            signupForm.addEventListener("submit", (event) => {
                event.preventDefault();
                const form = new FormData(signupForm);
                const username = String(form.get("username") || "").trim();
                const email = normalizeEmail(form.get("email"));
                const password = String(form.get("password") || "");
                const message = document.getElementById("profile-message");

                if (username.length < 3) {
                    if (message) {
                        message.textContent = "Username needs at least 3 characters.";
                    }
                    return;
                }
                if (!email.includes("@")) {
                    if (message) {
                        message.textContent = "Enter a valid email.";
                    }
                    return;
                }
                if (password.length < 6) {
                    if (message) {
                        message.textContent = "Password needs at least 6 characters.";
                    }
                    return;
                }
                if (state.accounts.some((account) => account.email === email)) {
                    if (message) {
                        message.textContent = "That email is already in use on this device.";
                    }
                    return;
                }

                const newAccount = {
                    username,
                    email,
                    password,
                    createdAt: new Date().toISOString(),
                };
                state.accounts.push(newAccount);
                saveJson(STORAGE_KEYS.accounts, state.accounts);

                const guestProgress = loadJson(STORAGE_KEYS.guestProgress, []);
                if (guestProgress.length) {
                    saveJson(`${STORAGE_KEYS.progressPrefix}${email}`, [...new Set(guestProgress)]);
                }

                saveJson(STORAGE_KEYS.guestProgress, []);
                setCurrentUser(newAccount);
            });
        }
        return;
    }

    const discoveredAnimals = state.animals.filter((animal) => state.discovered.includes(animal.id));
    const recent = discoveredAnimals.slice().reverse().slice(0, 6);

    body.innerHTML = `
        <div class="profile-hero">
            <div>
                <p class="eyebrow">Profile</p>
                <h1>${escapeHtml(state.currentUser.username || "Trainer")}</h1>
                <p class="region-subtitle">${escapeHtml(state.currentUser.email || "")}</p>
            </div>
            <button class="ghost-button profile-logout" id="logout-button" type="button">Logout</button>
        </div>

        <div class="profile-grid">
            <div class="profile-card">
                <span class="stat-label">Seen</span>
                <strong>${discoveredAnimals.length}/${state.animals.length}</strong>
            </div>
            <div class="profile-card">
                <span class="stat-label">Region</span>
                <strong>1</strong>
            </div>
            <div class="profile-card">
                <span class="stat-label">Type</span>
                <strong>Trainer</strong>
            </div>
            <div class="profile-card">
                <span class="stat-label">Status</span>
                <strong>Active</strong>
            </div>
        </div>

        <section class="profile-section">
            <p class="eyebrow">Recent Finds</p>
            <div class="profile-list">
                ${
                    recent.length
                        ? recent
                            .map((animal) => `
                                <button class="profile-item" type="button" data-open-entry data-animal-id="${escapeHtml(animal.id)}">
                                    <span aria-hidden="true">${escapeHtml(getAnimalEmoji(animal))}</span>
                                    <strong>${escapeHtml(animal.name)}</strong>
                                    <small>${escapeHtml(animal.category)}</small>
                                </button>
                            `)
                            .join("")
                        : `<div class="profile-empty">No discoveries yet. Start with Dog, Cat, or Sparrow.</div>`
                }
            </div>
        </section>

        <section class="profile-section">
            <p class="eyebrow">Account</p>
            <div class="profile-card">
                <span class="stat-label">Saved locally</span>
                <strong>Yes</strong>
                <p class="region-subtitle">We can wire Supabase auth later when you want synced accounts across devices.</p>
            </div>
        </section>
    `;

    const logoutButton = document.getElementById("logout-button");
    if (logoutButton) {
        logoutButton.addEventListener("click", () => {
            setCurrentUser(null);
        });
    }
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
        state.currentSuggestion = null;
        return;
    }

    state.currentSuggestion = suggestion;
    confirmName.textContent = suggestion.name;
    confirmDesc.textContent = `${suggestion.category} · ${suggestion.habitat}`;
    openEntry.dataset.animalId = suggestion.id;
    confirmPanel.classList.remove("is-hidden");
}

function getSuggestedMatch(label) {
    const normalizedLabel = normalizeText(label);
    const exact = state.animals.find((animal) => normalizeText(animal.name) === normalizedLabel);
    if (exact) {
        return exact;
    }

    const broadMatches = state.animals.filter((animal) => {
        const name = normalizeText(animal.name);
        const category = normalizeText(animal.category);
        return name.includes(normalizedLabel) || normalizedLabel.includes(name) || category === normalizedLabel;
    });

    if (broadMatches.length > 0) {
        return broadMatches[0];
    }

    return state.animals.find((animal) => animal.rarity !== "Legendary") || state.animals[0] || null;
}

async function loadBrowserRecognizer() {
    try {
        await ensureTensorflowRecognizer();
    } catch (_error) {
        state.recognizerError = _error && _error.message ? _error.message : String(_error || "Model bootstrap failed.");
        return null;
    }

    if (window.cocoSsd) {
        if (!state.recognizerPromise) {
            state.recognizerPromise = window.cocoSsd
                .load({
                    base: "lite_mobilenet_v2",
                    modelUrl: new URL("/static/vendor/coco-ssd/model.json", window.location.href).toString(),
                })
                .catch((error) => {
                    state.recognizerError = error && error.message ? error.message : String(error || "Model load failed.");
                    state.recognizerPromise = null;
                    throw error;
                });
        }
        return state.recognizerPromise;
    }
    return null;
}

function pickBrowserLabel(predictions) {
    if (!predictions || predictions.length === 0) {
        return null;
    }

    const best = predictions[0];
    const raw = String(best.class || "").toLowerCase();
    const mapped = BROAD_LABEL_MAP[raw] || best.class;
    return {
        label: mapped,
        confidence: best.score || 0,
        raw,
        predictions,
    };
}

async function startCamera() {
    const video = document.getElementById("camera-preview");
    const status = document.getElementById("scan-status");
    const result = document.getElementById("scan-result");

    if (!video || !status) {
        return;
    }

    try {
        if (state.currentCameraStream) {
            stopCamera();
        }

        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" } },
            audio: false,
        });

        state.currentCameraStream = stream;
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
    if (state.currentCameraStream) {
        state.currentCameraStream.getTracks().forEach((track) => track.stop());
        state.currentCameraStream = null;
    }

    const video = document.getElementById("camera-preview");
    if (video) {
        video.srcObject = null;
    }
}

async function captureAndRecognize() {
    const video = document.getElementById("camera-preview");
    const canvas = document.getElementById("capture-canvas");
    const status = document.getElementById("scan-status");
    const result = document.getElementById("scan-result");
    const stage = document.querySelector(".scan-stage");
    const frame = document.querySelector(".camera-frame");

    if (!video || !canvas || !status) {
        return;
    }

    if (!video.srcObject) {
        status.textContent = "Start the camera first.";
        return;
    }

    const setAnalyzingState = (enabled) => {
        if (stage) {
            stage.classList.toggle("is-analyzing", enabled);
        }
        if (frame) {
            frame.classList.toggle("is-analyzing", enabled);
        }
        if (status) {
            status.classList.toggle("is-analyzing", enabled);
        }
    };

    const width = video.videoWidth || 1280;
    const height = video.videoHeight || 720;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, width, height);

    setAnalyzingState(true);
    status.textContent = "Analyzing image...";

    let data = null;
    try {
        const model = await loadBrowserRecognizer();
        if (model) {
            state.recognizerError = null;
            const predictions = await model.detect(canvas);
            const chosen = pickBrowserLabel(predictions);
            if (chosen) {
                data = {
                    detected: chosen.label,
                    confidence: chosen.confidence,
                    alternatives: predictions.slice(1, 4).map((item) => ({
                        name: BROAD_LABEL_MAP[String(item.class || "").toLowerCase()] || item.class,
                        confidence: item.score || 0,
                    })),
                    note: chosen.raw === "bird"
                        ? "Bird detected. Use the Dex to confirm the exact bird."
                        : "Model prediction from the browser. Tap the closest Dex match to confirm.",
                };
            }
        }
    } catch (_error) {
        data = null;
    }

    if (!data) {
        data = {
            detected: "Unknown",
            confidence: 0.32,
            alternatives: [
                { name: "Dog", confidence: 0.18 },
                { name: "Cat", confidence: 0.11 },
                { name: "Crow", confidence: 0.09 },
            ],
            note: state.recognizerError
                ? `Recognition model error: ${state.recognizerError}`
                : "Recognition model could not load in this browser. The camera still works, but install a normal browser tab for best results.",
        };
    }

    try {
        status.textContent = "Scan complete.";
        if (result) {
            result.classList.remove("is-hidden");
            const detectedName = document.getElementById("detected-name");
            const detectedNote = document.getElementById("detected-note");
            const detectedAlt = document.getElementById("detected-alt");
            if (detectedName) {
                detectedName.textContent = `Detected: ${data.detected}`;
            }
            if (detectedNote) {
                detectedNote.textContent = data.note || "";
            }
            if (detectedAlt) {
                detectedAlt.textContent = (data.alternatives || [])
                    .map((item) => `${item.name} ${Math.round((item.confidence || 0) * 100)}%`)
                    .join(" | ");
            }
        }
    } finally {
        setAnalyzingState(false);
    }

    renderSuggestionPanel(getSuggestedMatch(data.detected));
}

function openEntryModal(animalId) {
    const animal = animalById(animalId);
    if (!animal) {
        return;
    }

    state.currentEntry = animal;

    const emojiNode = document.getElementById("entry-modal-emoji");
    const nameNode = document.getElementById("entry-modal-name");
    const scientificNode = document.getElementById("entry-modal-scientific");
    const descriptionNode = document.getElementById("entry-modal-description");
    const factNode = document.getElementById("entry-modal-fact");
    const rarityNode = document.getElementById("entry-modal-rarity");
    const regionNode = document.getElementById("entry-modal-region");
    const habitatNode = document.getElementById("entry-modal-habitat");
    const dietNode = document.getElementById("entry-modal-diet");
    const statusNode = document.getElementById("entry-modal-status");
    const categoryNode = document.getElementById("entry-modal-category");
    const discoverButton = document.getElementById("entry-modal-discover");

    if (emojiNode) emojiNode.textContent = getAnimalEmoji(animal);
    if (nameNode) nameNode.textContent = animal.name;
    if (scientificNode) scientificNode.textContent = animal.scientific_name;
    if (descriptionNode) descriptionNode.textContent = animal.description;
    if (factNode) factNode.textContent = animal.fact;
    if (rarityNode) {
        rarityNode.textContent = animal.rarity;
        rarityNode.className = `rarity-chip rarity-${formatRarityClass(animal.rarity)}`;
    }
    if (regionNode) regionNode.textContent = "Region 1";
    if (habitatNode) habitatNode.textContent = animal.habitat;
    if (dietNode) dietNode.textContent = animal.diet;
    if (statusNode) statusNode.textContent = animal.status;
    if (categoryNode) categoryNode.textContent = animal.category;
    if (discoverButton) {
        discoverButton.dataset.animalId = animal.id;
        discoverButton.dataset.mode = "modal";
        discoverButton.textContent = foundSet().has(animal.id) ? "Remove Discovery" : "Mark as Discovered";
    }

    const modal = document.getElementById("entry-modal");
    if (modal) {
        modal.classList.remove("is-hidden");
        modal.setAttribute("aria-hidden", "false");
    }
}

function closeEntryModal() {
    const modal = document.getElementById("entry-modal");
    if (modal) {
        modal.classList.add("is-hidden");
        modal.setAttribute("aria-hidden", "true");
    }
}

function markSuggestedAnimal() {
    if (!state.currentSuggestion) {
        return;
    }

    const discovered = new Set(state.discovered);
    discovered.add(state.currentSuggestion.id);
    persistDiscovered([...discovered]);

    const status = document.getElementById("scan-status");
    if (status) {
        status.textContent = `${state.currentSuggestion.name} added to your Dex.`;
    }
}

function renderNavActive() {
    const hash = window.location.hash || "#top";
    const map = [
        { selector: 'a[href="#top"]', active: hash === "#top" || hash === "" },
        { selector: 'a[href="#region-1"]', active: hash === "#region-1" },
        { selector: 'a[href="#profile-section"]', active: hash === "#profile-section" },
    ];

    map.forEach(({ selector, active }) => {
        const link = document.querySelector(selector);
        if (link) {
            link.classList.toggle("is-active", active);
        }
    });
}

function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) {
        return;
    }

    navigator.serviceWorker.register("/service-worker.js").catch(() => {
        // No-op: the app still works without the cache layer.
    });
}

function bindEvents() {
    const grid = document.getElementById("animal-grid");
    if (grid) {
        grid.addEventListener("click", (event) => {
            const openButton = event.target.closest("[data-open-entry]");
            if (openButton) {
                openEntryModal(openButton.dataset.animalId);
                return;
            }

            const discoverButton = event.target.closest("[data-discover-button]");
            if (discoverButton) {
                toggleAnimal(discoverButton.dataset.animalId);
            }
        });
    }

    const profileBody = document.getElementById("profile-body");
    if (profileBody) {
        profileBody.addEventListener("click", (event) => {
            const openButton = event.target.closest("[data-open-entry]");
            if (openButton) {
                openEntryModal(openButton.dataset.animalId);
            }
        });
    }

    const clearButton = document.getElementById("clear-progress");
    if (clearButton) {
        clearButton.addEventListener("click", () => {
            persistDiscovered([]);
        });
    }

    const searchInput = document.getElementById("search-input");
    if (searchInput) {
        searchInput.addEventListener("input", () => {
            const term = normalizeText(searchInput.value);
            document.querySelectorAll("[data-animal-card]").forEach((card) => {
                const haystack = normalizeText(card.dataset.search);
                card.classList.toggle("is-hidden", term !== "" && !haystack.includes(term));
            });
        });
    }

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

    const openEntrySuggestion = document.getElementById("open-entry");
    if (openEntrySuggestion) {
        openEntrySuggestion.addEventListener("click", () => {
            if (state.currentSuggestion) {
                openEntryModal(state.currentSuggestion.id);
            }
        });
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

    const entryModal = document.getElementById("entry-modal");
    const closeEntryBackdrop = document.getElementById("entry-modal-close");
    const closeEntryX = document.getElementById("entry-modal-x");
    const entryDiscover = document.getElementById("entry-modal-discover");

    if (closeEntryBackdrop) {
        closeEntryBackdrop.addEventListener("click", closeEntryModal);
    }
    if (closeEntryX) {
        closeEntryX.addEventListener("click", closeEntryModal);
    }
    if (entryDiscover) {
        entryDiscover.addEventListener("click", () => {
            const animalId = entryDiscover.dataset.animalId;
            if (animalId) {
                toggleAnimal(animalId);
                openEntryModal(animalId);
            }
        });
    }

    if (entryModal) {
        entryModal.addEventListener("click", (event) => {
            if (event.target === entryModal) {
                closeEntryModal();
            }
        });
    }

    window.addEventListener("hashchange", renderNavActive);
    window.addEventListener("beforeunload", stopCamera);
}

function init() {
    hydrateCurrentUser();
    renderDate();
    renderAnimals();
    renderProfile();
    bindEvents();
    registerServiceWorker();
    syncFoundStates();
    updateProgress();
    renderNavActive();

    if (!window.location.hash) {
        window.location.hash = "#top";
    }
}

document.addEventListener("DOMContentLoaded", init);
