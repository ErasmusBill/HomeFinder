/**
 * VacantHommie Admin - Dark/Light Theme Mode Toggle
 * Seamlessly toggles data-bs-theme & body.dark-mode with persistence.
 */

(function () {
  'use strict';

  function getSavedTheme() {
    let mode = localStorage.getItem('jazzmin-theme-mode');
    if (!mode || mode === 'auto') {
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      mode = prefersDark ? 'dark' : 'light';
    }
    return mode;
  }

  function applyTheme(mode, updateToggle = true) {
    const isDark = (mode === 'dark');
    document.documentElement.setAttribute('data-bs-theme', mode);
    if (document.body) {
      document.body.classList.toggle('dark-mode', isDark);
    }
    localStorage.setItem('jazzmin-theme-mode', mode);

    if (updateToggle) {
      const toggleBtn = document.getElementById('vh-theme-toggle-btn');
      if (toggleBtn) {
        const icon = toggleBtn.querySelector('i');
        if (icon) {
          icon.className = isDark ? 'fas fa-sun text-warning' : 'fas fa-moon';
        }
        toggleBtn.setAttribute('title', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
        toggleBtn.setAttribute('aria-label', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
      }
    }

    // Dispatch global event for charts and interactive components to re-render
    window.dispatchEvent(new CustomEvent('themeChanged', {
      detail: { mode: mode, isDark: isDark }
    }));
  }

  function setupThemeToggle() {
    // Check if toggle button already exists
    if (document.getElementById('vh-theme-toggle-btn')) return;

    const navContainer = document.querySelector('#jazzy-navbar .navbar-nav.ms-auto') ||
                         document.querySelector('#jazzy-navbar .navbar-nav.ml-auto') ||
                         document.querySelector('.app-header .navbar-nav.ms-auto');

    if (!navContainer) return;

    const currentMode = getSavedTheme();
    const isDark = (currentMode === 'dark');

    // Create nav item and toggle button
    const navItem = document.createElement('li');
    navItem.className = 'nav-item d-flex align-items-center me-2';

    const button = document.createElement('button');
    button.id = 'vh-theme-toggle-btn';
    button.type = 'button';
    button.className = 'nav-link btn btn-link px-2 py-1';
    button.style.cursor = 'pointer';
    button.style.border = 'none';
    button.style.background = 'transparent';
    button.style.fontSize = '1.1rem';
    button.style.transition = 'transform 0.2s ease, color 0.2s ease';
    button.setAttribute('title', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
    button.setAttribute('aria-label', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');

    button.innerHTML = `<i class="${isDark ? 'fas fa-sun text-warning' : 'fas fa-moon'}"></i>`;

    button.addEventListener('mouseenter', function() {
      button.style.transform = 'scale(1.18)';
    });
    button.addEventListener('mouseleave', function() {
      button.style.transform = 'scale(1)';
    });

    button.addEventListener('click', function (e) {
      e.preventDefault();
      const activeMode = document.documentElement.getAttribute('data-bs-theme') || getSavedTheme();
      const nextMode = (activeMode === 'dark') ? 'light' : 'dark';
      applyTheme(nextMode, true);
    });

    navItem.appendChild(button);

    // Insert before the user profile menu if present, otherwise append
    const userMenu = navContainer.querySelector('#jazzy-usermenu')?.closest('.nav-item') || navContainer.firstElementChild;
    if (userMenu) {
      navContainer.insertBefore(navItem, userMenu);
    } else {
      navContainer.appendChild(navItem);
    }

    // Ensure initial theme is applied to body
    applyTheme(currentMode, true);
  }

  // Initial sync before full load
  const initialMode = getSavedTheme();
  document.documentElement.setAttribute('data-bs-theme', initialMode);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupThemeToggle);
  } else {
    setupThemeToggle();
  }

  // Listen for system theme changes if user hasn't explicitly set a preference
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
      const saved = localStorage.getItem('jazzmin-theme-mode');
      if (!saved || saved === 'auto') {
        applyTheme(e.matches ? 'dark' : 'light', true);
      }
    });
  }
})();
