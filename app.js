'use strict';

let initialized = false;
let allGames = [];
let currentConsole = 'all';
const entriesPerPage = 250;
let currentPage = 1;
let sortColumn = null;
let sortOrder = 'asc';

const SORT_ASC = 'asc';
const SORT_DESC = 'desc';

let sortDirections = {
    'ID': null,
    'Title': null,
    'Console': null,
    'Parental Level': null
};

async function loadGames() {
    try {
        const response = await fetch('all.json');
        if (!response.ok) throw new Error('Failed to load all.json');
        const data = await response.json();

        allGames = Object.entries(data).map(([id, game]) => ({
            id,
            name: game.name || game.names?.[0]?.name || 'N/A',
            console: game.console || 'N/A',
            parentalLevel: game.parentalLevel || game['parental-level'] || 'N/A',
            icon: game.icon || game.icons?.[0]?.icon || '',
            details: game
        }));

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
    
    const prevButton = document.createElement('button');
    prevButton.textContent = 'Previous';
    prevButton.className = 'btn btn-sm btn-secondary me-2';
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
    nextButton.className = 'btn btn-sm btn-secondary ms-2';
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

        if (!isNaN(aValue) && !isNaN(bValue)) {
            aValue = parseFloat(aValue);
            bValue = parseFloat(bValue);
        }

        return sortOrder === 'asc' ? (aValue > bValue ? 1 : -1) : (aValue < bValue ? 1 : -1);
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
    const filterVal = document.getElementById('filter').value.toLowerCase();
    return allGames.filter(({ id, name, console }) => {
        const matchesConsole = currentConsole === 'all' || console.toLowerCase() === currentConsole.toLowerCase();
        const matchesFilter = `${id} ${name}`.toLowerCase().includes(filterVal);
        return matchesConsole && matchesFilter;
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

document.addEventListener('DOMContentLoaded', init);

async function init() {
    if (!initialized) {
        initialized = true;
        await loadGames();

        // Only add event listeners to nav links with data-console attribute
        document.querySelectorAll('.nav-link[data-console]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                currentConsole = link.getAttribute('data-console');
                currentPage = 1;
                renderTable();
                renderPagination();
            });
        });

        const filterInput = document.getElementById('filter');
        filterInput.addEventListener('input', () => {
            currentPage = 1;
            renderTable();
            renderPagination();
        });

        const clearButton = document.getElementById('clear_button');
        clearButton.addEventListener('click', () => {
            filterInput.value = '';
            currentPage = 1;
            renderTable();
            renderPagination();
        });

        filterInput.addEventListener('input', () => {
            if (filterInput.value.trim()) {
                clearButton.classList.remove('d-none');
            } else {
                clearButton.classList.add('d-none');
            }
        });
    }
}