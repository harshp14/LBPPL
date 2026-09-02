(function () {
    var root = document.documentElement;
    var schemeSelect = document.getElementById('scheme-select');
    var leagueSelect = document.getElementById('league-select');
    var known = {
        'bronze-night': true,
        'bronze-day': true,
        'obsidian-crimson': true,
        'cool-slate': true,
        'soft-parchment': true,
        'eros-blush': true,
        'cupid-velvet': true,
        sunset: true
    };
    var legacy = {
        slate: 'cool-slate',
        crimson: 'obsidian-crimson',
        ocean: 'bronze-day',
        forest: 'soft-parchment',
        royal: 'bronze-night'
    };

    function resolveScheme(scheme) {
        if (legacy[scheme]) {
            scheme = legacy[scheme];
        }
        return known[scheme] ? scheme : 'bronze-night';
    }

    function applyScheme(scheme) {
        scheme = resolveScheme(scheme);
        root.setAttribute('data-scheme', scheme);
        if (schemeSelect) {
            schemeSelect.value = scheme;
        }
    }

    applyScheme(root.getAttribute('data-scheme') || localStorage.getItem('draftleague-scheme') || 'bronze-night');

    if (schemeSelect) {
        schemeSelect.addEventListener('change', function () {
            var scheme = resolveScheme(schemeSelect.value);
            localStorage.setItem('draftleague-scheme', scheme);
            applyScheme(scheme);
        });
    }

    function setSeasonCookie(season) {
        document.cookie = 'draftleague-season=' + season + ';path=/;max-age=31536000';
    }

    if (leagueSelect) {
        var savedSeason = localStorage.getItem('draftleague-season') || '4';
        leagueSelect.value = savedSeason;
        setSeasonCookie(savedSeason);

        leagueSelect.addEventListener('change', function () {
            var season = leagueSelect.value;
            localStorage.setItem('draftleague-season', season);
            setSeasonCookie(season);
            if (leagueSelect.dataset.reloadOnChange === 'true') {
                window.location.reload();
            }
        });
    }
})();
