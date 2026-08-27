document.addEventListener('DOMContentLoaded', function () {
    var teamsEl = document.getElementById('teams-data');
    var agentsEl = document.getElementById('free-agents-data');
    var coachSelect = document.getElementById('fa-coach');
    var rowsContainer = document.getElementById('fa-rows');
    var addRowButton = document.getElementById('fa-add-row');
    if (!teamsEl || !agentsEl || !coachSelect || !rowsContainer || !addRowButton) return;

    var teams = JSON.parse(teamsEl.textContent);
    var freeAgents = JSON.parse(agentsEl.textContent);

    var dropItemsByCoach = {};
    teams.forEach(function (team) {
        dropItemsByCoach[team.coach_name] = team.pokemon.map(function (mon) {
            return { value: mon.name, label: mon.name + ' (' + mon.points + ' pts)' };
        });
    });

    var pickupItems = freeAgents.map(function (agent) {
        return { value: agent.name, label: agent.name + ' (' + agent.points + ' pts)' };
    });

    function fillOptions(select, items, placeholder) {
        var current = select.value;
        select.innerHTML = '';

        var placeholderOption = document.createElement('option');
        placeholderOption.value = '';
        placeholderOption.textContent = placeholder;
        select.appendChild(placeholderOption);

        items.forEach(function (item) {
            var option = document.createElement('option');
            option.value = item.value;
            option.textContent = item.label;
            select.appendChild(option);
        });

        if (items.some(function (item) { return item.value === current; })) {
            select.value = current;
        }
    }

    function refreshDropOptions() {
        var items = dropItemsByCoach[coachSelect.value] || [];
        rowsContainer.querySelectorAll('.fa-drop-select').forEach(function (select) {
            fillOptions(select, items, 'No drop');
        });
    }

    function addRow() {
        var row = document.createElement('div');
        row.className = 'fa-row';

        var dropSelect = document.createElement('select');
        dropSelect.name = 'drop';
        dropSelect.className = 'modal-input fa-drop-select';

        var pickupSelect = document.createElement('select');
        pickupSelect.name = 'pickup';
        pickupSelect.className = 'modal-input fa-pickup-select';

        row.appendChild(dropSelect);
        row.appendChild(pickupSelect);
        rowsContainer.appendChild(row);

        fillOptions(dropSelect, dropItemsByCoach[coachSelect.value] || [], 'No drop');
        fillOptions(pickupSelect, pickupItems, 'No pickup');
    }

    coachSelect.addEventListener('change', refreshDropOptions);
    addRowButton.addEventListener('click', addRow);

    rowsContainer.querySelectorAll('.fa-pickup-select').forEach(function (select) {
        fillOptions(select, pickupItems, 'No pickup');
    });
    refreshDropOptions();
});
