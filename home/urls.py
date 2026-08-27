from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('rosters/', views.rosters, name='rosters'),
    path('draft-board/', views.draft_board, name='draft_board'),
    path('schedule/', views.schedule, name='schedule'),
    path('schedule/submit-replay/', views.submit_replay, name='submit_replay'),
    path('statistics/', views.statistics, name='statistics'),
    path('free-agency-tracker/', views.free_agency_tracker, name='free_agency_tracker'),
    path('free-agency-tracker/submit/', views.submit_free_agency, name='submit_free_agency'),
]
