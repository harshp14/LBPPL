(function () {
    var root = document.documentElement;
    var schemeSelect = document.getElementById('scheme-select');
    var leagueSelect = document.getElementById('league-select');

    function applyScheme(scheme) {
        root.setAttribute('data-scheme', scheme);
        if (schemeSelect) {
            schemeSelect.value = scheme;
        }
    }

    applyScheme(root.getAttribute('data-scheme') || 'slate');

    if (schemeSelect) {
        schemeSelect.addEventListener('change', function () {
            var scheme = schemeSelect.value;
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
