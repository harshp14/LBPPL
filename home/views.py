from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.shortcuts import redirect, render
from django.urls import reverse

from . import data_access, replay_parser


VALID_SEASONS = {'1', '2', '3', '4'}
DEFAULT_SEASON = '4'


def _get_season(request):
    season = request.COOKIES.get('draftleague-season')
    return season if season in VALID_SEASONS else DEFAULT_SEASON


def index(request):
    season = _get_season(request)
    return render(request, 'home/index.html', {
        'content_template': f'home/home_content/s{season}.html',
    })


def changelog(request):
    return render(request, 'home/changelog.html')


def rosters(request):
    season = _get_season(request)
    teams = data_access.get_rosters(season)
    for team in teams:
        team['pokemon'] = sorted(team['pokemon'], key=lambda mon: mon['points'], reverse=True)
        for mon in team['pokemon']:
            mon['sprite'] = data_access.get_sprite_url(mon['name'], season)
    return render(request, 'home/rosters.html', {'teams': teams})


def draft_board(request):
    season = _get_season(request)
    columns = data_access.get_draft_board(season)
    drafted = {
        mon['name']
        for team in data_access.get_rosters(season)
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
                'sprite': data_access.get_sprite_url(name, season),
            } if name else None
            for name in row
        ]
        for row in cell_rows
    ]
    return render(request, 'home/draft_board.html', {'columns': columns, 'rows': rows})


def schedule(request):
    season = _get_season(request)
    weeks = data_access.get_schedule(season)
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
                mon['sprite'] = data_access.get_sprite_url(mon['pokemon'], season)
                mon['healing_received_total'] = data_access.healing_received_total(mon)

    return render(request, 'home/schedule.html', {
        'weeks': weeks,
        'selected_week': selected_week,
        'selected_match': selected_match,
        'selected_match_index': selected_match_index,
    })


def submit_replay(request):
    season = _get_season(request)
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
        ok, error = data_access.set_match_from_replay(season, week, match_index, replay_url)
        if ok:
            messages.success(request, 'Replay parsed - kills, deaths, and match stats are in.')
        else:
            messages.error(request, error)
    except replay_parser.ReplayParseError:
        if data_access.set_match_replay(season, week, match_index, replay_url):
            messages.warning(request, "Saved the link, but couldn't parse stats from that replay.")
        else:
            messages.error(request, "Couldn't find that match.")

    return redirect(f"{reverse('schedule')}?week={week}&match={match_index}")


def upcoming_games(request):
    season = _get_season(request)
    return render(request, 'home/upcoming_games.html', {
        'games': data_access.get_upcoming_games(season),
    })


def submit_game_time(request):
    season = _get_season(request)
    week = request.POST.get('week')
    match_index = request.POST.get('match_index')
    day = request.POST.get('day', '').strip()

    try:
        week = int(week)
        match_index = int(match_index)
    except (TypeError, ValueError):
        messages.error(request, "Couldn't find that match.")
        return redirect(reverse('schedule'))

    if not day:
        messages.error(request, "Pick a day first.")
        return redirect(f"{reverse('schedule')}?week={week}&match={match_index}")

    ok, error = data_access.set_match_game_time(season, week, match_index, day)
    if ok:
        messages.success(request, 'Game time sent to Discord.')
    else:
        messages.error(request, error)

    return redirect(f"{reverse('schedule')}?week={week}&match={match_index}")


def playoffs(request):
    season = _get_season(request)
    return render(request, 'home/playoffs.html', {'season': season})


def statistics(request):
    season = _get_season(request)
    return render(request, 'home/statistics.html', {'rows': data_access.get_statistics(season)})


def accolades(request):
    season = _get_season(request)
    accolades_data = data_access.get_accolades(season)
    for category in accolades_data['pokemon_awards']:
        for entry in category['entries']:
            entry['sprite'] = data_access.get_sprite_url(entry['pokemon'], season)
    return render(request, 'home/accolades.html', {'season': season, 'accolades': accolades_data})


def all_time_stats(request):
    return render(request, 'home/all_time_stats.html', {'rows': data_access.get_all_time_statistics()})


def free_agency_tracker(request):
    season = _get_season(request)
    teams = data_access.get_rosters(season)
    for team in teams:
        team['points_used'] = data_access.get_roster_points(team)
        team['free_agents_remaining'] = data_access.FREE_AGENT_CAP - team.get('free_agents_used', 0)

    return render(request, 'home/free_agency_tracker.html', {
        'teams': teams,
        'free_agents': data_access.get_free_agents(season),
        'log': data_access.get_free_agency_log(season),
        'points_cap': data_access.get_points_cap(season),
    })


def submit_free_agency(request):
    season = _get_season(request)
    coach = request.POST.get('coach', '').strip()
    drops = [name for name in request.POST.getlist('drop') if name]
    pickups = [name for name in request.POST.getlist('pickup') if name]

    success, error = data_access.submit_free_agency(season, coach, drops, pickups)
    if success:
        messages.success(request, f'Free agency move submitted for {coach}.')
    else:
        messages.error(request, error)

    return redirect(reverse('free_agency_tracker'))
