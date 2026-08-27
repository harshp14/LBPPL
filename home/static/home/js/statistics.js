(function () {
    const table = document.getElementById('stats-table');
    if (!table) return;

    const headers = [...table.querySelectorAll('thead th')];
    const tbody = table.querySelector('tbody');

    function currentValue(row, index) {
        const cell = row.children[index];
        return cell ? cell.dataset.value : '';
    }

    function sortBy(index, type, dir) {
        const rows = [...tbody.querySelectorAll('tr')];
        const sign = dir === 'asc' ? 1 : -1;

        rows.sort((a, b) => {
            const rawA = currentValue(a, index);
            const rawB = currentValue(b, index);
            const emptyA = rawA === '';
            const emptyB = rawB === '';
            if (emptyA || emptyB) {
                if (emptyA && emptyB) return 0;
                return emptyA ? 1 : -1; // empty always sinks to the bottom
            }
            if (type === 'num') {
                return (parseFloat(rawA) - parseFloat(rawB)) * sign;
            }
            return rawA.localeCompare(rawB) * sign;
        });

        rows.forEach((row) => tbody.appendChild(row));
    }

    headers.forEach((th, index) => {
        const type = th.dataset.sort;
        if (!type) return;

        th.classList.add('sortable');
        let dir = th.getAttribute('aria-sort') === 'ascending' ? 'asc'
            : th.getAttribute('aria-sort') === 'descending' ? 'desc'
            : null;

        th.addEventListener('click', () => {
            const defaultDir = th.dataset.defaultDir || (type === 'text' ? 'asc' : 'desc');
            dir = dir === null ? defaultDir : (dir === 'asc' ? 'desc' : 'asc');

            headers.forEach((h) => h.removeAttribute('aria-sort'));
            th.setAttribute('aria-sort', dir === 'asc' ? 'ascending' : 'descending');

            sortBy(index, type, dir);
        });
    });
})();
