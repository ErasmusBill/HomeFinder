
const favoriteButtons = document.querySelectorAll('.favorite-btn');

favoriteButtons.forEach((btn) => {
    btn.addEventListener('click', (e) => {
        e.preventDefault();

        const icon = btn.querySelector('i');

        if (icon.classList.contains('fa-regular')) {
            icon.classList.remove('fa-regular');
            icon.classList.add('fa-solid');
            icon.style.color = '#ef4444';
        } else {
            icon.classList.remove('fa-solid');
            icon.classList.add('fa-regular');
            icon.style.color = 'inherit';
        }
    });
});

// Simple search action alert simulation
const searchBtn = document.querySelector('.search-btn');

searchBtn.addEventListener('click', () => {
    alert('Searching for verified properties in Ghana...');
});