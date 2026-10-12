let locationsData = null;
let searchResults = [];
let selectedResults = new Set();
let selectedLocations = new Set();
let currentLocationType = null;

function $(id) {
    return document.getElementById(id);
}

function show(element) {
    if (element) element.classList.remove("hidden");
}

function hide(element) {
    if (element) element.classList.add("hidden");
}

async function copyText(text, button) {
    try {
        await navigator.clipboard.writeText(text);
        const original = button.textContent;
        button.textContent = "Copied!";
        setTimeout(() => { button.textContent = original; }, 1500);
    } catch (error) {
        console.error(error);
        alert("Unable to copy automatically. Please copy the text manually.");
    }
}

/* ============================================================
   SEARCH PAGE
   ============================================================ */

async function initializeSearchPage() {
    if (!$("clientNeed")) return;

    await loadLocations();
    setupLocationFilter();
    setupSearchButton();

    $("clientNeed").addEventListener("keydown", event => {
        if (event.key === "Enter") {
            event.preventDefault();
            performSearch();
        }
    });
}

async function loadLocations() {
    try {
        const response = await fetch("/api/locations");
        if (!response.ok) throw new Error("Could not load locations.");
        locationsData = await response.json();
    } catch (error) {
        console.error(error);
        locationsData = { regions: [], counties: [], cities: [] };
    }
}

function setupLocationFilter() {
    const toggle = $("locationToggle");
    const options = $("locationOptions");

    toggle.addEventListener("click", () => {
        const active = toggle.getAttribute("aria-pressed") === "true";
        const newState = !active;

        toggle.setAttribute("aria-pressed", String(newState));
        toggle.classList.toggle("active", newState);

        if (newState) {
            show(options);
        } else {
            hide(options);
            hide($("locationDropdownWrapper"));
            document.querySelectorAll('input[name="locationType"]').forEach(radio => {
                radio.checked = false;
            });
            $("locationSearch").value = "";
            delete $("locationSearch").dataset.value;
        }
    });

    document.querySelectorAll('input[name="locationType"]').forEach(radio => {
        radio.addEventListener("change", () => populateLocationDropdown(radio.value));
    });
}

function getLocationValues(type) {
    if (!locationsData) return [];

    // The API uses the exact keys "regions", "counties", and "cities".
    const keyByType = {
        region: "regions",
        county: "counties",
        city: "cities"
    };

    const values = locationsData[keyByType[type]] || [];
    return [...values].sort((a, b) => a.localeCompare(b));
}

function populateLocationDropdown(type) {
    const wrapper = $("locationDropdownWrapper");
    const input = $("locationSearch");
    const dropdown = $("locationDropdown");
    const values = getLocationValues(type);

    currentLocationType = type;
    selectedLocations.clear();

    show(wrapper);
    input.value = "";
    renderSelectedLocations();

    function render(filter = "") {
        const normalized = filter.toLowerCase().trim();
        dropdown.innerHTML = "";

        const matches = values.filter(value =>
            value.toLowerCase().includes(normalized)
        );

        if (!matches.length) {
            const empty = document.createElement("div");
            empty.className = "dropdown-empty";
            empty.textContent = "No matching locations";
            dropdown.appendChild(empty);
            return;
        }

        matches.forEach(value => {
            const label = document.createElement("label");
            label.className = "dropdown-option multi-option";

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = selectedLocations.has(value);

            checkbox.addEventListener("change", () => {
                if (checkbox.checked) {
                    selectedLocations.add(value);
                } else {
                    selectedLocations.delete(value);
                }

                renderSelectedLocations();
            });

            const text = document.createElement("span");
            text.textContent = value;

            label.append(checkbox, text);
            dropdown.appendChild(label);
        });
    }

    input.oninput = () => render(input.value);
    input.onfocus = () => render(input.value);
    render();
}


function renderSelectedLocations() {
    const container = $("selectedLocations");
    if (!container) return;

    container.innerHTML = "";

    selectedLocations.forEach(value => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "location-chip";
        chip.textContent = `${value} ×`;
        chip.title = `Remove ${value}`;

        chip.addEventListener("click", () => {
            selectedLocations.delete(value);
            renderSelectedLocations();

            if (currentLocationType) {
                $("locationSearch").dispatchEvent(
                    new Event("input")
                );
            }
        });

        container.appendChild(chip);
    });
}


function setupSearchButton() {
    $("searchButton").addEventListener("click", performSearch);
}

async function performSearch() {
    const query = $("clientNeed").value.trim();
    const error = $("searchError");
    hide(error);

    if (!query) {
        error.textContent = "Please enter what the client needs.";
        show(error);
        $("clientNeed").focus();
        return;
    }

    const filterEnabled =
        $("locationToggle").getAttribute("aria-pressed") === "true";

    let locationType = null;
    let locationValue = null;

    if (filterEnabled) {
        const selectedType = document.querySelector(
            'input[name="locationType"]:checked'
        );

        if (!selectedType) {
            error.textContent = "Please choose Region, County, or City.";
            show(error);
            return;
        }

        locationType = selectedType.value;
        locationValue = Array.from(selectedLocations);

        if (!locationValue.length) {
            error.textContent =
                "Please select at least one location from the list.";
            show(error);
            return;
        }
    }

    const button = $("searchButton");
    button.disabled = true;
    button.textContent = "Searching...";

    try {
        const response = await fetch("/api/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                query,
                location_type: locationType,
                location_values: locationValue
            })
        });

        const data = await response.json();

        if (!response.ok) throw new Error(data.error || "Search failed.");

        sessionStorage.setItem("searchData", JSON.stringify(data));
        window.location.href = "/results";
    } catch (err) {
        console.error(err);
        error.textContent = err.message || "Something went wrong.";
        show(error);
    } finally {
        button.disabled = false;
        button.textContent = "Search";
    }
}

/* ============================================================
   RESULTS PAGE
   ============================================================ */

function initializeResultsPage() {
    if (!$("resultsList")) return;

    const stored = sessionStorage.getItem("searchData");

    if (!stored) {
        window.location.href = "/";
        return;
    }

    try {
        const data = JSON.parse(stored);
        searchResults = data.results || [];

        renderResults(data.query, data.location_type, data.location_value);
        setupResultButtons();
        updateEmailTemplate();
    } catch (error) {
        console.error(error);
        window.location.href = "/";
    }
}

function renderResults(query, locationType, locationValue) {
    $("resultsTitle").textContent = `Results for "${query}"`;

    if (
        locationType &&
        locationValue &&
        (Array.isArray(locationValue)
            ? locationValue.length
            : true)
    ) {
        const label =
            locationType.charAt(0).toUpperCase() +
            locationType.slice(1);

        const values = Array.isArray(locationValue)
            ? locationValue.join(", ")
            : locationValue;

        $("resultsLocation").textContent =
            `in ${values} (${label}):`;
    } else {
        $("resultsLocation").textContent = "in Nebraska:";
    }

    const container = $("resultsList");
    container.innerHTML = "";

    if (!searchResults.length) {
        show($("noResults"));
        return;
    }

    hide($("noResults"));

    searchResults.forEach((resource, index) => {
        container.appendChild(createResultElement(resource, index));
    });
}

function createResultElement(resource, index) {
    const wrapper = document.createElement("div");
    wrapper.className = "resource";
    wrapper.dataset.index = index;
    wrapper.setAttribute("role", "button");
    wrapper.setAttribute("tabindex", "0");

    const selector = document.createElement("button");
    selector.className = "resource-selector";
    selector.type = "button";
    selector.setAttribute("aria-label", `Select ${resource.organization || "resource"}`);

    const content = document.createElement("div");
    content.className = "resource-content";

    const organization = document.createElement("h3");
    organization.textContent = resource.organization || "";

    const fields = [
        ["Services provided", resource.services_provided],
        ["Persons served", resource.persons_served],
        ["Area served", resource.location?.raw],
        ["Website", resource.website],
        ["Phone number", resource.contact],
        ["How client can obtain service", resource.how_to_obtain]
    ];

    content.appendChild(organization);

    fields.forEach(([label, value]) => {
        if (!value) return;

        const row = document.createElement("div");
        const strong = document.createElement("strong");
        strong.textContent = `${label}: `;
        row.appendChild(strong);
        row.appendChild(document.createTextNode(value));
        content.appendChild(row);
    });

    selector.addEventListener("click", event => {
        event.stopPropagation();
        toggleSelection(index);
    });

    wrapper.addEventListener("click", () => toggleSelection(index));
    wrapper.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            toggleSelection(index);
        }
    });

    wrapper.appendChild(selector);
    wrapper.appendChild(content);

    return wrapper;
}

function toggleSelection(index) {
    if (selectedResults.has(index)) {
        selectedResults.delete(index);
    } else {
        selectedResults.add(index);
    }

    updateSelectionDisplay();
    updateEmailTemplate();
}

function updateSelectionDisplay() {
    document.querySelectorAll(".resource").forEach(element => {
        const index = Number(element.dataset.index);
        const selected = selectedResults.has(index);

        element.classList.toggle("selected", selected);

        const button = element.querySelector(".resource-selector");
        button.textContent = selected ? "✓" : "";
        button.setAttribute("aria-pressed", String(selected));
    });
}

function setupResultButtons() {
    $("selectAllButton").addEventListener("click", () => {
        searchResults.forEach((_, index) => selectedResults.add(index));
        updateSelectionDisplay();
        updateEmailTemplate();
    });

    $("clearButton").addEventListener("click", () => {
        selectedResults.clear();
        updateSelectionDisplay();
        updateEmailTemplate();
    });

    $("copySelectionButton").addEventListener("click", copySelectedResources);

    $("copyEmailButton").addEventListener("click", () => {
        copyText($("emailTemplate").innerText, $("copyEmailButton"));
    });

    $("backButton").addEventListener("click", () => {
        window.location.href = "/";
    });
}

function copySelectedResources() {
    const selected = Array.from(selectedResults).map(index => searchResults[index]);

    if (!selected.length) {
        alert("Please select at least one resource.");
        return;
    }

    copyText(
        selected.map(formatResourceForCopy).join("\n\n"),
        $("copySelectionButton")
    );
}

function formatResourceForCopy(resource) {
    const lines = [];

    if (resource.organization) lines.push(resource.organization);
    if (resource.services_provided) {
        lines.push(`Services provided: ${resource.services_provided}`);
    }
    if (resource.contact) lines.push(`Phone: ${resource.contact}`);
    if (resource.website) lines.push(`Website: ${resource.website}`);
    if (resource.how_to_obtain) {
        lines.push(`How to obtain service: ${resource.how_to_obtain}`);
    }

    return lines.join("\n");
}

/* ============================================================
   EMAIL TEMPLATE
   ============================================================ */

function updateEmailTemplate() {
    const organizations = Array.from(selectedResults)
        .map(index => searchResults[index]);

    const organizationText = organizations.length
        ? organizations.map(formatOrganizationForEmail).join("\n\n")
        : "[Selected resources will appear here.]";

    const template = `Dear :

You have let us know that you and your family might need help finding some other types of resources.  The following describes resources that may be available from different agencies in Nebraska. Please feel free to contact these resources as described below.
 
${organizationText}

Sincerely,`;

    $("emailTemplate").textContent = template;
}

function formatOrganizationForEmail(resource) {
    const lines = [];

    if (resource.organization) lines.push(resource.organization);
    if (resource.services_provided) {
        lines.push(`Services: ${resource.services_provided}`);
    }
    if (resource.contact) lines.push(`Phone: ${resource.contact}`);
    if (resource.website) lines.push(`Website: ${resource.website}`);
    if (resource.how_to_obtain) {
        lines.push(resource.how_to_obtain);
    }

    return lines.join(" | ");
}

document.addEventListener("DOMContentLoaded", () => {
    initializeSearchPage();
    initializeResultsPage();
});
