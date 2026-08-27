from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.shortcuts import redirect, render
from django.urls import reverse

from . import data_access, replay_parser


def index(request):
    return render(request, 'home/index.html')


def rosters(request):
    teams = data_access.get_rosters()
    for team in teams:
        for mon in team['pokemon']:
            mon['sprite'] = data_access.get_sprite_url(mon['name'])
    return render(request, 'home/rosters.html', {'teams': teams})


def draft_board(request):
    columns = data_access.get_draft_board()
    drafted = {
        mon['name']
        for team in data_access.get_rosters()
        for mon in team['pokemon']
    }
    max_rows = max((len(c['pokemon']) for c in columns), default=0)
    for column in columns:
        column['pokemon'] += [None] * (max_rows - len(column['pokemon']))
    cell_rows = list(zip(*(column['pokemon'] for column in columns)))
    rows = [
        [
            {
                'name': name,
                'drafted': name in drafted,
                'sprite': data_access.get_sprite_url(name),
            } if name else None
            for name in row
        ]
        for row in cell_rows
    ]
    return render(request, 'home/draft_board.html', {'columns': columns, 'rows': rows})


def schedule(request):
    weeks = data_access.get_schedule()
    for week in weeks:
        week['played'] = sum(1 for m in week['matches'] if m['winner'])
        week['total'] = len(week['matches'])

    default_week = next(
        (w['week'] for w in weeks if w['played'] < w['total']),
        weeks[-1]['week'] if weeks else None,
    )
    try:
        selected_week_num = int(request.GET.get('week', default_week))
    except (TypeError, ValueError):
        selected_week_num = default_week

    selected_week = next((w for w in weeks if w['week'] == selected_week_num), None) or (weeks[0] if weeks else None)

    selected_match = None
    selected_match_index = 0
    if selected_week and selected_week['matches']:
        try:
            selected_match_index = int(request.GET.get('match', 0))
        except (TypeError, ValueError):
            selected_match_index = 0
        if not (0 <= selected_match_index < len(selected_week['matches'])):
            selected_match_index = 0

        selected_match = selected_week['matches'][selected_match_index]
        stats = selected_match.get('stats')
        if stats:
            for mon in stats['player1'] + stats['player2']:
                mon['sprite'] = data_access.get_sprite_url(mon['pokemon'])

    return render(request, 'home/schedule.html', {
        'weeks': weeks,
        'selected_week': selected_week,
        'selected_match': selected_match,
        'selected_match_index': selected_match_index,
    })


def submit_replay(request):
    week = request.POST.get('week')
    match_index = request.POST.get('match_index')
    replay_url = request.POST.get('replay_url', '').strip()

    try:
        week = int(week)
        match_index = int(match_index)
        URLValidator(schemes=['http', 'https'])(replay_url)
    except (TypeError, ValueError, ValidationError):
        messages.error(request, "That doesn't look like a valid link.")
        return redirect(f"{reverse('schedule')}?week={week}&match={match_index}")

    try:
        ok, error = data_access.set_match_from_replay(week, match_index, replay_url)
        if ok:
            messages.success(request, 'Replay parsed - kills, deaths, and match stats are in.')
        else:
            messages.error(request, error)
    except replay_parser.ReplayParseError:
        if data_access.set_match_replay(week, match_index, replay_url):
            messages.warning(request, "Saved the link, but couldn't parse stats from that replay.")
        else:
            messages.error(request, "Couldn't find that match.")

    return redirect(f"{reverse('schedule')}?week={week}&match={match_index}")


def statistics(request):
    return render(request, 'home/statistics.html', {'rows': data_access.get_statistics()})


def free_agency_tracker(request):
    teams = data_access.get_rosters()
    for team in teams:
        team['points_used'] = data_access.get_roster_points(team)
        team['free_agents_remaining'] = data_access.FREE_AGENT_CAP - team.get('free_agents_used', 0)

    return render(request, 'home/free_agency_tracker.html', {
        'teams': teams,
        'free_agents': data_access.get_free_agents(),
        'log': data_access.get_free_agency_log(),
        'points_cap': data_access.POINTS_CAP,
    })


def submit_free_agency(request):
    coach = request.POST.get('coach', '').strip()
    drops = [name for name in request.POST.getlist('drop') if name]
    pickups = [name for name in request.POST.getlist('pickup') if name]

    success, error = data_access.submit_free_agency(coach, drops, pickups)
    if success:
        messages.success(request, f'Free agency move submitted for {coach}.')
    else:
        messages.error(request, error)

    return redirect(reverse('free_agency_tracker'))
