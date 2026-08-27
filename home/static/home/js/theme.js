(function () {
    var root = document.documentElement;
    var swatches = document.querySelectorAll('.scheme-swatch');

    function applyScheme(scheme) {
        root.setAttribute('data-scheme', scheme);
        swatches.forEach(function (btn) {
            btn.setAttribute('aria-pressed', btn.getAttribute('data-scheme') === scheme ? 'true' : 'false');
        });
    }

    applyScheme(root.getAttribute('data-scheme') || 'slate');

    swatches.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var scheme = btn.getAttribute('data-scheme');
            localStorage.setItem('draftleague-scheme', scheme);
            applyScheme(scheme);
        });
    });
})();
