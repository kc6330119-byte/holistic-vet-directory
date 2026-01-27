/**
 * Holistic Vet Directory - Main JavaScript
 */

(function() {
    'use strict';

    // ==========================================================================
    // Mobile Menu Toggle
    // ==========================================================================
    const mobileMenuToggle = document.querySelector('.mobile-menu-toggle');
    const mainNav = document.querySelector('.main-nav');

    if (mobileMenuToggle && mainNav) {
        mobileMenuToggle.addEventListener('click', function() {
            const isExpanded = this.getAttribute('aria-expanded') === 'true';
            this.setAttribute('aria-expanded', !isExpanded);
            mainNav.classList.toggle('is-open');
            document.body.classList.toggle('menu-open');
        });
    }

    // ==========================================================================
    // Search Overlay Toggle
    // ==========================================================================
    const searchToggle = document.querySelector('.search-toggle');
    const searchOverlay = document.querySelector('.search-overlay');
    const searchInput = searchOverlay?.querySelector('.search-input');

    if (searchToggle && searchOverlay) {
        searchToggle.addEventListener('click', function() {
            const isActive = searchOverlay.classList.toggle('active');
            searchOverlay.setAttribute('aria-hidden', !isActive);

            if (isActive && searchInput) {
                searchInput.focus();
            }
        });

        // Close on Escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && searchOverlay.classList.contains('active')) {
                searchOverlay.classList.remove('active');
                searchOverlay.setAttribute('aria-hidden', 'true');
            }
        });
    }

    // ==========================================================================
    // Smooth Scroll for Anchor Links
    // ==========================================================================
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;

            const target = document.querySelector(targetId);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });

                // Update URL without scrolling
                history.pushState(null, null, targetId);
            }
        });
    });

    // ==========================================================================
    // Lazy Loading Images
    // ==========================================================================
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                    }
                    observer.unobserve(img);
                }
            });
        }, {
            rootMargin: '50px 0px'
        });

        document.querySelectorAll('img[data-src]').forEach(img => {
            imageObserver.observe(img);
        });
    }

    // ==========================================================================
    // Sort Select Handler
    // ==========================================================================
    const sortSelect = document.getElementById('sort-select');
    if (sortSelect) {
        sortSelect.addEventListener('change', function() {
            const vetList = document.querySelector('.vet-list');
            if (!vetList) return;

            const cards = Array.from(vetList.querySelectorAll('.vet-card'));
            const sortBy = this.value;

            cards.sort((a, b) => {
                const aTitle = a.querySelector('.vet-card__title')?.textContent.trim() || '';
                const bTitle = b.querySelector('.vet-card__title')?.textContent.trim() || '';

                if (sortBy === 'name') {
                    return aTitle.localeCompare(bTitle);
                }

                if (sortBy === 'state') {
                    const aLocation = a.querySelector('.vet-card__location')?.textContent.trim() || '';
                    const bLocation = b.querySelector('.vet-card__location')?.textContent.trim() || '';
                    return aLocation.localeCompare(bLocation);
                }

                return 0;
            });

            // Remove ads temporarily
            const ads = Array.from(vetList.querySelectorAll('.ad-unit, .ad-placeholder'));
            ads.forEach(ad => ad.remove());

            // Re-append sorted cards
            cards.forEach(card => vetList.appendChild(card));
        });
    }

    // ==========================================================================
    // Filter Toggle (Mobile)
    // ==========================================================================
    const filterToggle = document.querySelector('.filter-toggle');
    const filterSidebar = document.querySelector('.listing-sidebar');

    if (filterToggle && filterSidebar) {
        filterToggle.addEventListener('click', function() {
            filterSidebar.classList.toggle('is-visible');
        });
    }

    // ==========================================================================
    // Click-to-Call Phone Numbers
    // ==========================================================================
    document.querySelectorAll('a[href^="tel:"]').forEach(link => {
        link.addEventListener('click', function() {
            // Analytics tracking could go here
            console.log('Phone click:', this.href);
        });
    });

    // ==========================================================================
    // External Links - Open in New Tab
    // ==========================================================================
    document.querySelectorAll('a[href^="http"]').forEach(link => {
        if (!link.href.includes(window.location.hostname)) {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
        }
    });

    // ==========================================================================
    // Sticky Header Shadow
    // ==========================================================================
    const header = document.querySelector('.site-header');
    if (header) {
        let lastScroll = 0;

        window.addEventListener('scroll', function() {
            const currentScroll = window.pageYOffset;

            if (currentScroll > 10) {
                header.classList.add('is-scrolled');
            } else {
                header.classList.remove('is-scrolled');
            }

            lastScroll = currentScroll;
        }, { passive: true });
    }

    // ==========================================================================
    // Form Validation
    // ==========================================================================
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = this.querySelectorAll('[required]');
            let isValid = true;

            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    isValid = false;
                    field.classList.add('is-invalid');
                } else {
                    field.classList.remove('is-invalid');
                }
            });

            if (!isValid) {
                e.preventDefault();
                const firstInvalid = this.querySelector('.is-invalid');
                if (firstInvalid) {
                    firstInvalid.focus();
                }
            }
        });
    });

    // ==========================================================================
    // Geolocation for "Near Me" Searches
    // ==========================================================================
    window.getUserLocation = function(callback) {
        if ('geolocation' in navigator) {
            navigator.geolocation.getCurrentPosition(
                function(position) {
                    callback(null, {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude
                    });
                },
                function(error) {
                    callback(error, null);
                },
                {
                    enableHighAccuracy: false,
                    timeout: 5000,
                    maximumAge: 300000 // 5 minutes
                }
            );
        } else {
            callback(new Error('Geolocation not supported'), null);
        }
    };

    // ==========================================================================
    // Calculate Distance Between Two Points
    // ==========================================================================
    window.calculateDistance = function(lat1, lon1, lat2, lon2) {
        const R = 3959; // Earth's radius in miles
        const dLat = toRad(lat2 - lat1);
        const dLon = toRad(lon2 - lon1);
        const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                  Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
                  Math.sin(dLon / 2) * Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;

        function toRad(deg) {
            return deg * (Math.PI / 180);
        }
    };

    // ==========================================================================
    // Copy to Clipboard
    // ==========================================================================
    window.copyToClipboard = function(text, button) {
        navigator.clipboard.writeText(text).then(function() {
            const originalText = button.textContent;
            button.textContent = 'Copied!';
            setTimeout(function() {
                button.textContent = originalText;
            }, 2000);
        }).catch(function(err) {
            console.error('Could not copy text:', err);
        });
    };

    // ==========================================================================
    // Print Page
    // ==========================================================================
    document.querySelectorAll('.print-button').forEach(button => {
        button.addEventListener('click', function() {
            window.print();
        });
    });

    // ==========================================================================
    // Back to Top Button
    // ==========================================================================
    const backToTop = document.querySelector('.back-to-top');
    if (backToTop) {
        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 500) {
                backToTop.classList.add('is-visible');
            } else {
                backToTop.classList.remove('is-visible');
            }
        }, { passive: true });

        backToTop.addEventListener('click', function(e) {
            e.preventDefault();
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }

    // ==========================================================================
    // Accessibility: Focus Visible Polyfill
    // ==========================================================================
    document.body.addEventListener('mousedown', function() {
        document.body.classList.add('using-mouse');
    });

    document.body.addEventListener('keydown', function(e) {
        if (e.key === 'Tab') {
            document.body.classList.remove('using-mouse');
        }
    });

    // ==========================================================================
    // Google Maps Initialization (if map element exists)
    // ==========================================================================
    window.initMap = window.initMap || function() {
        const mapContainers = document.querySelectorAll('[data-lat][data-lng]');

        mapContainers.forEach(container => {
            if (typeof google === 'undefined') return;

            const lat = parseFloat(container.dataset.lat);
            const lng = parseFloat(container.dataset.lng);
            const name = container.dataset.name || 'Location';

            if (isNaN(lat) || isNaN(lng)) return;

            const map = new google.maps.Map(container, {
                center: { lat, lng },
                zoom: 15,
                mapTypeControl: false,
                streetViewControl: false,
                styles: [
                    {
                        featureType: 'poi',
                        elementType: 'labels',
                        stylers: [{ visibility: 'off' }]
                    }
                ]
            });

            new google.maps.Marker({
                position: { lat, lng },
                map: map,
                title: name
            });
        });
    };

    // ==========================================================================
    // Service Worker Registration (for PWA)
    // ==========================================================================
    if ('serviceWorker' in navigator && window.location.protocol === 'https:') {
        window.addEventListener('load', function() {
            navigator.serviceWorker.register('/sw.js').then(function(registration) {
                console.log('ServiceWorker registered:', registration.scope);
            }).catch(function(error) {
                console.log('ServiceWorker registration failed:', error);
            });
        });
    }

    // ==========================================================================
    // Console Message
    // ==========================================================================
    console.log('%cHolistic Vet Directory', 'color: #2D6A4F; font-size: 24px; font-weight: bold;');
    console.log('%cHelping pets find natural care', 'color: #52B788; font-size: 14px;');

})();
