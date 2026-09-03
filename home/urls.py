from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('rosters/', views.rosters, name='rosters'),
    path('draft-board/', views.draft_board, name='draft_board'),
    path('schedule/', views.schedule, name='schedule'),
    path('standings/', views.standings, name='standings'),
    path('schedule/submit-replay/', views.submit_replay, name='submit_replay'),
    path('schedule/submit-game-time/', views.submit_game_time, name='submit_game_time'),
    path('prep-sheet/', views.prep_sheet, name='prep_sheet'),
    path('upcoming-games/', views.upcoming_games, name='upcoming_games'),
    path('playoffs/', views.playoffs, name='playoffs'),
    path('statistics/', views.statistics, name='statistics'),
    path('accolades/', views.accolades, name='accolades'),
    path('all-time-stats/', views.all_time_stats, name='all_time_stats'),
    path('free-agency-tracker/', views.free_agency_tracker, name='free_agency_tracker'),
    path('free-agency-tracker/submit/', views.submit_free_agency, name='submit_free_agency'),
    path('changelog/', views.changelog, name='changelog'),
    path('api/schedule/', views.schedule_api, name='schedule_api'),
]
