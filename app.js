'use strict';

let initialized = false;
let allGames = [];
let currentConsole = 'all';
const entriesPerPage = 250;
let currentPage = 1;
let sortColumn = 'name';
let sortOrder = 'asc';
let debounceTimer;

const SORT_ASC = 'asc';
const SORT_DESC = 'desc';

let sortDirections = {
    'ID': null,
    'Title': null,
    'Console': null,
    'Parental Level': null
};

function CleanTitle(title) {
    let charr = title.split("").map(c => c.charCodeAt(0));
    const arrLen = charr.length;
    for (let i = 0; i < arrLen; i++) {
        const ch = charr[i];
        if (ch > 0xff00 && ch <= 0xff5e) {
            charr[i] = ch - 0xfee0;
        }
        else if (ch > 0x30a0 && ch <= 0x30f6) {
            charr[i] = ch - 0x0060;
        }
    }
    return charr.map(c => String.fromCharCode(c)).join("")
        .toLowerCase()
        .replaceAll('[', '')
        .replaceAll(']', '')
        .replaceAll('(tm)', '')
        .replaceAll(' ™', '')
        .replaceAll('™', '')
        .replaceAll('(r)', '')
        .replaceAll(' ®', '')
        .replaceAll('®', ' ')
        .replaceAll('\u3000', ' ')
        .replaceAll('\r\n', ' ')
        .replaceAll('\r', ' ')
        .replaceAll('\n', ' ')
        .replaceAll('    ', ' ')
        .replaceAll('   ', ' ')
        .replaceAll('  ', ' ')
        .replaceAll('\u00B7', '・')
        .replaceAll('\uFF65', '・')
        .replaceAll('\u2160', 'I')
        .replaceAll('\u2161', 'II')
        .replaceAll('\u2162', 'III')
        .replaceAll('\u2163', 'IV')
        .replaceAll('\u2164', 'V')
        .replaceAll('\u2165', 'VI')
        .replaceAll('core4', 'core4')
        .replaceAll('baлл•и', 'валли')
        .replaceAll('disgaea3', 'disgaea 3')
        .replaceAll('disgaea4', 'disgaea 4')
        .replaceAll('l@ve', 'love')
        .replaceAll('prototype2', 'prototype 2')
        .replaceAll('singstar vol.', 'singstar vol ')
        .replaceAll('skate.', 'skate 1');
}

async function loadGames() {
    try {
        const response = await fetch('all.json.gz');
        if (!response.ok) throw new Error('Failed to load all.json.gz');

        const stream = response.body.pipeThrough(new DecompressionStream('gzip'));
        const text = await new Response(stream).text();

        const data = JSON.parse(text);

        allGames = Object.entries(data).map(([id, game]) => {
            const name = game.name || game.names?.[0]?.name || 'N/A';
            return {
                id,
                name: name,
                console: game.console || 'N/A',
                parentalLevel: game.parentalLevel || game['parental-level'] || 'N/A',
                icon: game.icon || game.icons?.[0]?.icon || '',
                details: game,
                filterId: id.toLowerCase().replace(/[-\s]/g, ''),
                filterName: CleanTitle(name)
            };
        });

        allGames.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));

        renderPagination();
        renderTable();
    } catch (error) {
        console.error('Error loading games:', error);
    } finally {
        document.getElementById('loading_progress').classList.add('d-none');
        document.getElementById('table_container').classList.remove('d-none');
    }
}

// Render the table with pagination
function renderTable() {
    const tbody = document.querySelector('#table tbody');
    tbody.innerHTML = '';

    let filteredGames = filterGames();
    if (sortColumn) {
        filteredGames = sortGames(filteredGames);
    }

    const start = (currentPage - 1) * entriesPerPage;
    const end = start + entriesPerPage;
    const gamesToDisplay = filteredGames.slice(start, end);

    gamesToDisplay.forEach(({ id, name, console, parentalLevel, icon, details }) => {
        const row = document.createElement('tr');
        row.classList.add('game-row');
        row.innerHTML = `
            <td>${id}</td>
            <td>${name}</td>
            <td>${console}</td>
            <td>${parentalLevel}</td>
            <td>
                ${icon ? `<button class="btn btn-sm btn-primary" onclick="loadIcon(this, '${icon}', event)">Show Icon</button>` : 'N/A'}
            </td>
        `;
        row.addEventListener('click', () => toggleDetails(row, details));
        tbody.appendChild(row);
    });
    
    document.getElementById('game_count').textContent = `Showing ${start + 1}-${Math.min(end, filteredGames.length)} of ${filteredGames.length} games`;
}

function loadIcon(button, iconUrl, event) {
    event.stopPropagation();

    const img = document.createElement('img');
    img.src = iconUrl;
    img.width = 250;
    img.alt = 'Game Icon';

    img.addEventListener('click', (e) => {
        e.stopPropagation();
        img.replaceWith(button);
    });

    button.replaceWith(img);
}

// Toggle game details
function toggleDetails(row, details) {
    if (row.nextElementSibling && row.nextElementSibling.classList.contains('details-row')) {
        row.nextElementSibling.remove();
        return;
    }

    const detailsRow = document.createElement('tr');
    detailsRow.classList.add('details-row');
    detailsRow.innerHTML = `
        <td colspan="5">
            ${Object.entries(details).map(([key, value]) => `<strong>${key}:</strong> ${JSON.stringify(value)}`).join('<br>')}
        </td>
    `;
    row.after(detailsRow);
}

// Render pagination controls
function renderPagination() {
    const pagination = document.getElementById('pagination');
    pagination.innerHTML = '';

    const filteredGames = filterGames();
    const totalPages = Math.ceil(filteredGames.length / entriesPerPage);

    if (totalPages <= 1) return;

    const prevButton = document.createElement('button');
    prevButton.textContent = 'Previous';
    prevButton.className = 'btn btn-sm btn-primary me-2';
    prevButton.disabled = currentPage === 1;
    prevButton.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            renderTable();
            renderPagination();
        }
    });
    pagination.appendChild(prevButton);

    const pageInput = document.createElement('input');
    pageInput.type = 'number';
    pageInput.min = 1;
    pageInput.max = totalPages;
    pageInput.value = currentPage;
    pageInput.className = 'form-control form-control-sm d-inline w-auto';
    pageInput.addEventListener('change', (e) => {
        const newPage = parseInt(e.target.value);
        if (newPage >= 1 && newPage <= totalPages) {
            currentPage = newPage;
            renderTable();
            renderPagination();
        } else {
            pageInput.value = currentPage;
        }
    });
    pagination.appendChild(pageInput);

    const nextButton = document.createElement('button');
    nextButton.textContent = 'Next';
    nextButton.className = 'btn btn-sm btn-primary ms-2';
    nextButton.disabled = currentPage === totalPages;
    nextButton.addEventListener('click', () => {
        if (currentPage < totalPages) {
            currentPage++;
            renderTable();
            renderPagination();
        }
    });
    pagination.appendChild(nextButton);
}

// Sort games
function sortGames(games) {
    return games.sort((a, b) => {
        let aValue = a[sortColumn];
        let bValue = b[sortColumn];

        if (!isNaN(aValue) && !isNaN(bValue) && aValue !== '' && bValue !== '') {
            aValue = parseFloat(aValue);
            bValue = parseFloat(bValue);
        } else {
            aValue = aValue.toString().toLowerCase();
            bValue = bValue.toString().toLowerCase();
        }

        if (aValue === bValue) return 0;
        const result = aValue > bValue ? 1 : -1;
        return sortOrder === 'asc' ? result : -result;
    });
}

// Handle sorting when clicking table headers
document.querySelectorAll('#table th').forEach((th, index) => {
    th.addEventListener('click', () => {
        sortColumn = ['id', 'name', 'console', 'parentalLevel'][index];
        sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
        renderTable();
    });
});

// Filter games
function filterGames() {
    const val = document.getElementById('filter').value?.toLowerCase().trim();
    const normalizedVal = val.replace(/[-\s]/g, '');

    return allGames.filter((game) => {
        const matchesConsole = currentConsole === 'all' || game.console.toLowerCase() === currentConsole.toLowerCase();
        if (!matchesConsole) return false;

        if (val.length > 0) {
            return game.filterId.includes(normalizedVal) || game.filterName.includes(val);
        }
        return true;
    });
}

// To top button
window.onscroll = function() {scrollFunction()};
function scrollFunction() {
  if (document.body.scrollTop > 20 || document.documentElement.scrollTop > 20) {
    document.getElementById("scrollToTopBtn").style.display = "block";
  } else {
    document.getElementById("scrollToTopBtn").style.display = "none";
  }
}
function scrollToTop() {
  document.body.scrollTop = 0;
  document.documentElement.scrollTop = 0;
}

// Dark mode functions
function toggleDarkMode() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-bs-theme') === 'dark';
    html.setAttribute('data-bs-theme', isDark ? 'light' : 'dark');
    localStorage.setItem('darkMode', !isDark);
    updateDarkModeIcon();
}

function updateDarkModeIcon() {
    const toggleBtn = document.getElementById('darkModeToggle');
    const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    toggleBtn.innerHTML = isDark ? '<i class="bi bi-sun"></i>' : '<i class="bi bi-moon"></i>';
    toggleBtn.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
}

function initializeDarkMode() {
    // Check for saved preference or use system preference
    const savedMode = localStorage.getItem('darkMode');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    if (savedMode === 'true' || (savedMode === null && systemPrefersDark)) {
        document.documentElement.setAttribute('data-bs-theme', 'dark');
    }
    updateDarkModeIcon();
    // Set up toggle button
    document.getElementById('darkModeToggle').addEventListener('click', toggleDarkMode);
}

function updateActiveFilter() {
    document.querySelectorAll('.nav-link[data-console]').forEach(link => {
        link.classList.remove('active-filter');
    });

    const activeLink = document.querySelector(`.nav-link[data-console="${currentConsole}"]`);
    if (activeLink) {
        activeLink.classList.add('active-filter');
    }
}

document.addEventListener('DOMContentLoaded', init);

async function init() {
    if (!initialized) {
        initialized = true;
        initializeDarkMode();
        updateActiveFilter();
        await loadGames();

        // Only add event listeners to nav links with data-console attribute
        document.querySelectorAll('.nav-link[data-console]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                currentConsole = link.getAttribute('data-console');
                currentPage = 1;
                updateActiveFilter();
                renderTable();
                renderPagination();
            });
        });

        const filterInput = document.getElementById('filter');
        const clearButton = document.getElementById('clear_button');

        filterInput.addEventListener('input', () => {
            clearTimeout(debounceTimer);

            if (filterInput.value.trim()) {
                clearButton.classList.remove('d-none');
            } else {
                clearButton.classList.add('d-none');
            }

            debounceTimer = setTimeout(() => {
                currentPage = 1;
                renderTable();
                renderPagination();
            }, 200);
        });

        clearButton.addEventListener('click', () => {
            filterInput.value = '';
            clearButton.classList.add('d-none');
            currentPage = 1;
            renderTable();
            renderPagination();
        });

        window.addEventListener('keydown', (event) => {
            if (event.code === 'Escape') {
                filterInput.value = '';
                clearButton.classList.add('d-none');
                currentPage = 1;
                renderTable();
                renderPagination();
            }
        });
    }
}